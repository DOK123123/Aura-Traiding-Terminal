"""Manual offline runner for a separate Linux/WSL research host, never Render.

init/enqueue/run/verify/backup/restore are explicit commands. No loop, cron or HTTP dispatch.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
from app.lab.models import LabError,canonical
from app.research.persistence import ROOT,MARKER,initialize,location,configured_store


def state_store(path,*,readonly=False):
    return configured_store(writable=not readonly,env={'AURA_RESEARCH_STATE_DIR':str(location(path)),'AURA_RESEARCH_STORAGE_MODE':'durable'})

@contextmanager
def runner_lock(directory):
    import fcntl
    p=directory/'runner.lock'
    if p.is_symlink():raise LabError('RESEARCH_STORAGE_CONFLICT')
    with p.open('a+b') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise LabError('BUSY') from None
        yield f.fileno()


def sandbox_child(args):
    if os.getenv('RENDER') or not args.isolated_host:raise LabError('RESEARCH_ISOLATED_HOST_REQUIRED')
    import resource
    import socket
    # Apply before importing replay/context/indicators or reading large artifacts.
    resource.setrlimit(resource.RLIMIT_AS,(args.memory_mib*1024**2,)*2)
    resource.setrlimit(resource.RLIMIT_CPU,(args.cpu_seconds,args.cpu_seconds+1))
    resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,)*2)
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    signal.alarm(args.wall_seconds+2)
    original=socket.socket.connect;original_ex=socket.socket.connect_ex
    def connect(sock,address):
        if sock.family in (socket.AF_INET,socket.AF_INET6):raise LabError('WORKER_NETWORK_FORBIDDEN')
        return original(sock,address)
    def connect_ex(sock,address):
        if sock.family in (socket.AF_INET,socket.AF_INET6):raise LabError('WORKER_NETWORK_FORBIDDEN')
        return original_ex(sock,address)
    socket.socket.connect=connect;socket.socket.connect_ex=connect_ex
    store=state_store(args.state_dir);row=store.get(args.job_id)
    if row['attempt']!=args.attempt or (row['state']!='RUNNING' if args.command=='_child' else row['report'] is None):raise LabError('RESEARCH_ALREADY_PROCESSED')
    if args.command=='_verify':
        from app.research.experiment import execute
        from app.research.data import load_dataset
        store.verify_chunks(args.job_id)
        bars,source=load_dataset();result=execute(row['config'],bars,source)
        if result['checksum']!=row['report']['logical_report_checksum']:raise LabError('REPRODUCIBILITY_ERROR')
        return
    from app.research.experiment import execute
    from app.research.data import load_dataset
    bars,source=load_dataset();result=execute(row['config'],bars,source)
    store.finish(args.job_id,result,attempt=args.attempt)


def supervise(args):
    if os.getenv('RENDER') or not args.isolated_host or not sys.platform.startswith('linux'):raise LabError('RESEARCH_ISOLATED_LINUX_HOST_REQUIRED')
    path=location(args.state_dir);store=state_store(path)
    with runner_lock(path) as fd:
        import resource
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        import shutil
        if shutil.disk_usage(path).free<512*1024**2:raise LabError('WORKER_DISK_HEADROOM_REQUIRED')
        verifying=args.command=='verify'
        row=store.get(args.job_id) if verifying else None
        if verifying and row['report'] is None:raise LabError('RESEARCH_NOT_FOUND')
        claim=dict(attempt=row['attempt']) if verifying else store.claim(args.job_id)
        attempt=claim['attempt'];start=time.monotonic()
        cmd=[sys.executable,'-m','scripts.research_runner','_verify' if verifying else '_child','--state-dir',str(path),'--job-id',args.job_id,'--attempt',attempt,'--isolated-host',
            '--wall-seconds',str(args.wall_seconds),'--cpu-seconds',str(args.cpu_seconds),'--memory-mib',str(args.memory_mib)]
        # Deliberate allowlist: no exchange, Supabase, owner, LLM keys, proxies or scheduler settings.
        env={'PATH':os.defpath,'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
        proc=None;failure=None
        try:
            proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,pass_fds=(fd,))
            try:code=proc.wait(timeout=args.wall_seconds)
            except subprocess.TimeoutExpired:

                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait();failure='WORKER_WALL_LIMIT';code=proc.returncode
            if code and failure is None:failure='WORKER_RESOURCE_OR_EXECUTION_FAILED'
        finally:
            if proc is not None and proc.poll() is None:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait()
            row=store.get(args.job_id)
            if not verifying and row['state']=='RUNNING' and row['attempt']==attempt:
                store.finish(args.job_id,None,failure or 'WORKER_INTERRUPTED',attempt=attempt)
        row=store.get(args.job_id);usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        return dict(worker_pid=proc.pid,supervisor_pid=os.getpid(),worker_peak_rss_mib=usage.ru_maxrss/1024,supervisor_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,cpu_seconds_used=usage.ru_utime+usage.ru_stime-before.ru_utime-before.ru_stime,id=args.job_id,state='ERROR' if verifying and failure else row['state'],error=failure if verifying else row['error'],verified=bool(verifying and not failure),elapsed_seconds=time.monotonic()-start,
            separate_process=True,network_disabled=True,environment_allowlisted=True,limits=dict(memory_mib=args.memory_mib,cpu_seconds=args.cpu_seconds,wall_seconds=args.wall_seconds),
            logical_checksum=row['report']['logical_report_checksum'] if row['report'] else None)


def backup(args):
    import shutil
    source=location(args.state_dir);store=state_store(source,readonly=True);dest=location(args.dest)
    if dest.exists():raise LabError('RESEARCH_STORAGE_CONFLICT')
    dest.mkdir(mode=0o700,parents=True)
    with store.connect() as src,sqlite3.connect(dest/store.path.name) as dst:src.backup(dst)
    shutil.copyfile(source/MARKER,dest/MARKER)
    checked=state_store(dest,readonly=True)
    for row in checked.list():
        if checked.get(row['id'])['report']:checked.verify_chunks(row['id'])
    return dict(status='BACKUP_CREATED',storage_id=json.loads((dest/MARKER).read_text())['storage_id'],budget_history_preserved=True)


def restore(args):
    import shutil
    source=location(args.backup_dir);original=state_store(source,readonly=True);dest=location(args.state_dir)
    if dest.exists():raise LabError('RESEARCH_STORAGE_CONFLICT')
    dest.mkdir(parents=True,mode=0o700)
    shutil.copyfile(source/MARKER,dest/MARKER);shutil.copyfile(original.path,dest/original.path.name)
    restored=state_store(dest)
    for row in restored.list():
        if restored.get(row['id'])['report']:restored.verify_chunks(row['id'])
    return dict(status='RESTORED_OFFLINE',budget_history_preserved=True,automatic_run=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for name in ('init','enqueue','run','recover','retry','backup','restore','inspect','verify','_child','_verify'):
        cmd=sub.add_parser(name);cmd.add_argument('--state-dir',required=True,type=Path)
        if name=='enqueue':cmd.add_argument('--hypothesis',choices=['MEAN_REVERSION','LIQUIDITY_SWEEP','VOLATILITY_BREAKOUT','REGIME_SWITCHING'],required=True)
        if name in ('run','retry','inspect','verify','_child','_verify'):cmd.add_argument('--job-id',required=True)
        if name in ('run','verify','_child','_verify'):
            cmd.add_argument('--isolated-host',action='store_true');cmd.add_argument('--wall-seconds',type=int,default=180,choices=range(5,301));cmd.add_argument('--cpu-seconds',type=int,default=120,choices=range(5,181));cmd.add_argument('--memory-mib',type=int,default=768,choices=range(256,2049))
        if name in ('_child','_verify'):cmd.add_argument('--attempt',required=True)
        if name=='backup':cmd.add_argument('--dest',required=True,type=Path)
        if name=='restore':cmd.add_argument('--backup-dir',required=True,type=Path)
    a=p.parse_args(argv)
    try:
        if os.getenv('RENDER') and a.command not in ('inspect','backup'):raise LabError('RESEARCH_LOCAL_WORKBENCH_REQUIRED')
        if a.command=='init':initialize(a.state_dir);result=dict(status='INITIALIZED_DURABLE_DIRECTORY_NOT_HARDWARE_ATTESTATION')
        elif a.command in ('run','verify'):result=supervise(a)
        elif a.command in ('_child','_verify'):sandbox_child(a);return 0
        elif a.command=='backup':result=backup(a)
        elif a.command=='restore':result=restore(a)
        else:
            store=state_store(a.state_dir,readonly=a.command=='inspect')
            if a.command=='enqueue':
                from app.research.experiment import frozen_config
                from app.research.data import available
                result=dict(id=store.enqueue(frozen_config(a.hypothesis,available())),state='QUEUED')
            elif a.command=='recover':result=dict(interrupted=store.interrupt_stale(),automatic_run=False)
            elif a.command=='retry':store.retry(a.job_id);result=dict(state='QUEUED',automatic_run=False)
            else:result=store.get(a.job_id)
        print(json.dumps(result,separators=(',',':')))
        return 1 if result.get('state')=='ERROR' else 0
    except (LabError,OSError,ValueError,TypeError,KeyError,sqlite3.Error) as e:
        code=e.code if isinstance(e,LabError) else 'RESEARCH_RUNNER_FAILED'
        print(json.dumps(dict(status='ERROR',code=code)));return 1

if __name__=='__main__':raise SystemExit(main())
