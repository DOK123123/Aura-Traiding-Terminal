"""PAPER EXECUTION TEST HARNESS. CLI only, new temporary SQLite per subcase.

Fabricated deterministic inputs ONLY; no real market/strategy performance proof.
No configurable DB path, no Service.configured(), no network or Supabase access.
"""
import argparse
import asyncio
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal as D
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import sys
from unittest.mock import patch

from app.automated.service import Service
from app.automated.storage import SQLiteStore,SupabaseStore
from app.automated.engine import DemoError,POLICY
from app.lab.models import digest,canonical
from scripts.verify_auto42_execution import TestMarket,seed_store,bar
from scripts.paper_e2e_oracle import audit_position,audit_mark,audit_close,check

ROOT=Path(__file__).resolve().parents[1]
SCHEMA='PAPER_EXECUTION_E2E_1'
FILES=('app/automated/engine.py','app/automated/strategy.py','app/automated/service.py','app/automated/storage.py',
 'app/automated/live_monitor.py','app/automated/api.py','scripts/auto42_scheduler.py','scripts/auto42_schema.sql',
 'scripts/verify_auto42_execution.py','scripts/verify_paper_e2e.py','scripts/paper_e2e_oracle.py')

def code_hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}

@contextmanager
def isolated():
    original=socket.socket.connect;original_ex=socket.socket.connect_ex
    def deny(sock,address):
        if sock.family in (socket.AF_INET,socket.AF_INET6):raise AssertionError('HARNESS_NETWORK_FORBIDDEN')
        return original(sock,address)
    def deny_ex(sock,address):
        if sock.family in (socket.AF_INET,socket.AF_INET6):raise AssertionError('HARNESS_NETWORK_FORBIDDEN')
        return original_ex(sock,address)
    def forbid(*a,**k):raise AssertionError('HARNESS_SUPABASE_FORBIDDEN')
    with patch.object(socket.socket,'connect',deny),patch.object(socket.socket,'connect_ex',deny_ex),patch.object(SupabaseStore,'__init__',forbid),patch.dict('os.environ',RENDER='',RENDER_GIT_COMMIT=''),patch('app.automated.service.scheduler_configured',return_value=True):
        yield

class Session:
    def __init__(self,side,label):
        self.market=TestMarket(side);self.now=[self.market.bars[-1].time+930];self.label=label
        self.folder=tempfile.TemporaryDirectory(prefix='aura-e2e-');self.path=Path(self.folder.name)/'auto-paper-42.sqlite3';self.services=[]
    async def start(self):
        self.store=await seed_store(self.path,self.now,'HARNESS_ONLY_'+self.label)
        self.svc=self.service(self.store);await self.svc.control('START','a'*32)
        self.starting=(await self.store.load())['state']['balance'];check(self.starting=='10000','INITIAL_BALANCE')
    def service(self,store=None):
        s=Service(self.market,store or SQLiteStore(self.path,clock=lambda:self.now[0]),clock=lambda:self.now[0]);self.services.append(s);return s
    async def add(self,**kw):
        self.market.add(**kw);self.now[0]+=900;return await self.svc.tick()
    async def queue(self):
        await self.add();s=(await self.store.load())['state'];check(s['pending'] is not None and s['position'] is None,'SIGNAL_NEXT_OPEN')
    async def open(self):
        await self.queue();await self.add();self.position=deepcopy((await self.store.load())['state']['position'])
        check(self.position is not None,'OPEN');audit_position(self.position);self.market.signal=False
    async def mark(self):
        await self.add(c='100.8' if self.market.side=='LONG' else '99.2')
        s=(await self.store.load())['state'];view=await self.svc.live_monitor();audit_mark(self.position,s,self.market.bars[-1],view)
        self.mark_proof=dict(marked_at=s['last_mark_at'],equity=s['equity'],net_pnl=view['position']['net_pnl_including_entry_fee'])
    async def close_trade(self,kind):
        p=self.position;stop,target=D(p['stop_loss']),D(p['take_profit']);long=p['direction']=='LONG';kw={}
        if kind=='BOTH':kw=dict(h=str(max(stop,target)+1),l=str(min(stop,target)-1))
        elif kind=='TP':kw={'h':str(target+1)} if long else {'l':str(target-1)}
        elif kind=='SL':kw={'l':str(stop-1)} if long else {'h':str(stop+1)}
        elif kind=='STOP_GAP':
            px=stop-2 if long else stop+2;kw=dict(o=str(px),h=str(px+1),l=str(px-1),c=str(px))
        elif kind=='TP_GAP':
            px=target+2 if long else target-2;kw=dict(o=str(px),h=str(px+1),l=str(px-1),c=str(px))
        else:raise ValueError('UNKNOWN_TEST_EXIT')
        await self.add(**kw)
    async def rows(self):return await self.store.history(limit=200)
    async def report(self,checks=None):
        envelope=await self.store.load();state=envelope['state'];rows=await self.rows();opens=[r['payload'] for r in rows if r['kind']=='OPEN'];closes=[r['payload'] for r in rows if r['kind']=='CLOSE']
        check(len(opens)==len(closes)==1,'EXACTLY_ONCE_OPEN_CLOSE')
        entry_bar=next(b for b in self.market.bars if b.time==self.position['entry_time'])
        check(D(self.position['entry_raw_price'])==entry_bar.open and self.position['entry_time']==self.position['signal_at'],'NEXT_OPEN_SOURCE_PRICE')
        audit_close(self.position,closes[0],state,self.market.bars[-1]);view=await self.svc.live_monitor()
        check(view['status']=='WAITING_FOR_REAL_SIGNAL' and not view['live_cycle_verified'],'NEVER_LIVE_VERIFIED')
        events=[r['payload'] for r in rows if r['kind']=='LIVE_MONITOR']
        check(any(e['event_type']=='POSITION_UPDATE' for e in events),'POSITION_UPDATE')
        check(all(not e['origin']['production_evidence'] and e['origin']['backend']=='SQLITE_DEVELOPMENT_ONLY' for e in events),'LOCAL_PROVENANCE')
        t=closes[0]
        return dict(status='PASS',test_only=True,starting_balance=self.starting,direction=t['direction'],
            entry_price=t['entry_price'],entry_raw_price=t['entry_raw_price'],exit_raw_price=t['exit_raw_price'],entry_time=t['entry_time'],exit_time=t['exit_time'],risk_usdt=t['risk_usdt'],risk_budget_usdt=t['risk_budget_usdt'],size=t['size'],stop_loss=t['stop_loss'],take_profit=t['take_profit'],exit_price=t['exit_price'],
            entry_fee=t['entry_fee'],exit_fee=t['exit_fee'],fees=t['fees'],slippage=state['slippage'],net_pnl=t['realized_pnl'],final_balance=state['balance'],
            actual_open_count=len(opens),actual_close_count=len(closes),exit_reason=t['exit_reason'],position_update=self.mark_proof,
            position_id=t['id'],monitor_status=view['status'],live_cycle_verified=False,oracle='EXACT_FRACTION_INDEPENDENT',
            checks=checks or {},event_types=sorted({e['event_type'] for e in events}),
            journal_digest=digest(rows),fixture_sha256=digest([b.data() for b in self.market.bars]))
    async def cleanup(self):
        for s in self.services:await s.close()
        self.folder.cleanup()


def restart_worker(path,market,now,connection):
    """Fresh Python interpreter (spawn), no inherited Service/store/account object."""
    async def work():
        p=Path(path);check(p.name=='auto-paper-42.sqlite3' and p.parent.name.startswith('aura-e2e-') and p.parent.parent.resolve()==Path(tempfile.gettempdir()).resolve(),'WORKER_TEMP_SCOPE')
        store=SQLiteStore(p,clock=lambda:now);svc=Service(market,store,clock=lambda:now)
        try:
            before=await store.load();check(before['state']['position'] is not None,'CHILD_RESTORE_OPEN')
            result=await svc.tick();after=await store.load();check(result['duplicate'] and before==after,'CHILD_DUPLICATE_TICK')
            view=await svc.live_monitor();check(not view['live_cycle_verified'],'CHILD_NOT_LIVE')
            return dict(position=after['state']['position'],revision=after['revision'],worker_pid=os.getpid(),duplicate=True,monitor_status=view['status'])
        finally:await svc.close()
    try:
        with isolated():connection.send(dict(ok=True,result=asyncio.run(work())))
    except BaseException:connection.send(dict(ok=False,error='ISOLATED_RESTART_WORKER_FAILED'))
    finally:connection.close()

async def fresh_process(session):
    ctx=multiprocessing.get_context('spawn');parent,child=ctx.Pipe(duplex=False)
    proc=ctx.Process(target=restart_worker,args=(str(session.path),session.market,session.now[0],child));proc.start();child.close()
    try:
        ready=await asyncio.to_thread(parent.poll,15)
        if not ready:raise AssertionError('RESTART_CHILD_TIMEOUT')
        result=parent.recv();await asyncio.to_thread(proc.join,5)
        check(result['ok'] and proc.exitcode==0,'NEW_PROCESS_RECOVERY');check(result['result']['position']==session.position,'PERSISTED_POSITION_EXACT')
        proof=result['result'];check(proof.pop('worker_pid')==proc.pid and proc.pid!=os.getpid(),'DISTINCT_WORKER_PID');proof['pid_distinct']=True
        return proof
    finally:
        if proc.is_alive():proc.terminate();await asyncio.to_thread(proc.join,5)
        parent.close()

@contextmanager
def fail_inside_transaction(store,probe):
    with store.connect() as c:c.execute("CREATE TRIGGER harness_abort AFTER UPDATE ON auto42_account BEGIN SELECT harness_abort(); END")
    original=store.connect
    @contextmanager
    def fault_connection():
        with original() as c:
            def abort():
                probe['attempted_open_rows']=c.execute("select count(*) from auto42_events where kind='OPEN'").fetchone()[0]
                probe['attempted_revision']=c.execute('select revision from auto42_account where id=1').fetchone()[0]
                raise sqlite3.OperationalError('DUMMY_TRANSACTION_FAILURE')
            c.create_function('harness_abort',0,abort);yield c
    try:
        with patch.object(store,'connect',fault_connection):yield
    finally:
        with original() as c:c.execute('DROP TRIGGER harness_abort')

async def abort_open(session):
    await session.queue();before=await session.store.load();rows=await session.rows();probe={}
    session.market.add();session.now[0]+=900
    with fail_inside_transaction(session.store,probe):
        try:await session.svc.tick()
        except DemoError as e:check(e.code=='STORAGE_UNAVAILABLE','FAULT_ERROR_CODE')
        else:raise AssertionError('FAULT_DID_NOT_ABORT')
    after=await session.store.load();check(before==after and rows==await session.rows(),'ATOMIC_ROLLBACK')
    check(probe['attempted_open_rows']==1 and probe['attempted_revision']==before['revision']+1,'FAILURE_AFTER_ACTUAL_WRITES')
    view=await session.svc.live_monitor();check(view['status']=='FAILED' and view['last_open'] is None,'NO_PHANTOM_OPEN')
    return dict(atomic_state_events_watermark_rollback=True,failed_after_account_update=True,attempted_open_rows=1,
        committed_open_rows=0,committed_close_rows=0,revision_unchanged=True,monitor_during_failure=view['status'])

async def concurrent_open(session):
    await session.queue();session.market.add();session.now[0]+=900
    other_store=SQLiteStore(session.path,clock=lambda:session.now[0]);other=session.service(other_store)
    arrived=[];release=asyncio.Event()
    originals=[session.store.commit,other_store.commit]
    def wrapped(index):
        async def commit(revision,state,events,key):
            arrived.append(revision)
            if len(arrived)==2:release.set()
            await asyncio.wait_for(release.wait(),10)
            return await originals[index](revision,state,events,key)
        return commit
    with patch.object(session.store,'commit',wrapped(0)),patch.object(other_store,'commit',wrapped(1)):
        result=await asyncio.wait_for(asyncio.gather(session.svc.tick(),other.tick()),15)
    check(len(arrived)==2 and arrived[0]==arrived[1],'FORCED_CONCURRENT_SAME_REVISION')
    check(sum(x['opened_positions'] for x in result)==1 and sum(x['duplicate'] for x in result)==1,'RACE_EXACTLY_ONCE')
    session.position=deepcopy((await session.store.load())['state']['position']);session.market.signal=False
    return dict(two_controller_instances=True,same_revision_barrier=True,winning_opens=1,duplicate_loser=1)

async def scheduler_open(session):
    import httpx
    from fastapi import FastAPI
    from app.automated.api import router
    from scripts import auto42_scheduler as scheduler
    await session.queue();session.market.add();session.now[0]+=900
    app=FastAPI();app.state.auto42=session.svc;app.include_router(router)
    loop=asyncio.get_running_loop();codes=[];lines=[];calls=[];dummy='DUMMY_E2E_SCHEDULER_TOKEN_'+'x'*32
    class Response:
        status=200
        def __init__(self,raw):self.raw=raw
        def read(self,limit):return self.raw[:limit]
        def __enter__(self):return self
        def __exit__(self,*a):pass
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://harness.invalid') as client:
        class InProcessOpener:
            def open(self,request,timeout):
                check(request.full_url=='https://'+scheduler.HOST+scheduler.PATH,'SCHEDULER_FIXED_CONTRACT')
                future=asyncio.run_coroutine_threadsafe(client.post('/api/auto42/tick',headers=dict(request.header_items())),loop)
                response=future.result(10);check(response.status_code==200,'ASGI_TICK');calls.append(response.json());return Response(response.content)
        with patch.dict('os.environ',AURA_AUTO42_SCHEDULER_SECRET=dummy),patch('app.automated.api.scheduler_configured',return_value=True):
            check((await client.post('/api/auto42/tick')).status_code==401,'SCHEDULER_AUTH_REQUIRED')
            for _ in range(3):
                code=await asyncio.to_thread(scheduler.run,env={'AURA_AUTO42_TICK_URL':'https://'+scheduler.HOST+scheduler.PATH,'AURA_AUTO42_SCHEDULER_SECRET':dummy},opener=InProcessOpener(),emit=lines.append)
                codes.append(code)
    check(codes==[0,0,0] and sum(x['opened_positions'] for x in calls)==1 and all(x['duplicate'] for x in calls[1:]),'SCHEDULER_REPEATED_TICKS')
    session.position=deepcopy((await session.store.load())['state']['position']);session.market.signal=False
    return dict(real_scheduler_client=True,in_process_ASGI_only=True,auth_rejected_without_token=True,runs=3,
        first_open=1,repeated_opens=0,exit_codes=codes,safe_output=lines)

async def lifecycle(label,side,kind,variant=None):
    session=Session(side,label)
    try:
        await session.start();checks={}
        if variant=='failure':
            checks=await abort_open(session);s=(await session.store.load())['state']
            return dict(status='PASS',test_only=True,starting_balance='10000',direction=side,entry_price=None,size=None,
                stop_loss=s['pending']['stop_loss'],take_profit=s['pending']['take_profit'],exit_price=None,fees='0',slippage='0',net_pnl='0',final_balance=s['balance'],
                actual_open_count=0,actual_close_count=0,oracle='NO_COMMITTED_TRADE_BALANCE_UNCHANGED',checks=checks,
                monitor_status='FAILED_DURING_INJECTED_WRITE_FAILURE',live_cycle_verified=False)
        if variant=='recovery':
            checks=await abort_open(session);await session.svc.tick()
            session.position=deepcopy((await session.store.load())['state']['position']);check(session.position is not None,'SAME_CANDLE_RECOVERY_OPEN');session.market.signal=False
            checks.update(same_candle_retry=True,watermark_resumed=True,monitor_after_recovery=(await session.svc.live_monitor())['status'])
        elif variant=='concurrent':checks=await concurrent_open(session)
        elif variant=='scheduler':checks=await scheduler_open(session)
        else:await session.open()
        if variant=='restart':
            await session.svc.close();checks=await fresh_process(session)
            session.store=SQLiteStore(session.path,clock=lambda:session.now[0]);session.svc=session.service(session.store)
            check((await session.store.load())['state']['position']==session.position,'PARENT_REOPEN_POSITION')
        if variant=='same_candle':
            before=await session.store.load();count=len(await session.rows());session.now[0]+=300;result=await session.svc.tick();after=await session.store.load()
            check(result['tick_outcome']=='NO_NEW_CANDLE' and not result['processed_this_run'],'SAME_CANDLE_NEW_SLOT')
            check(after['state']['position']==before['state']['position'] and after['state']['balance']==before['state']['balance'],'NO_DUPLICATE_FINANCIAL_CHANGE')
            check(len(await session.rows())>count,'NEW_SCHEDULER_SLOT_RECORDED');checks=dict(new_slot_same_candle=True,financial_state_unchanged=True)
        await session.mark();await session.close_trade(kind)
        # Repeated same-run CLOSE tick must not add a trade or any journal rows.
        before=await session.store.load();rows=await session.rows();result=await session.svc.tick()
        check(result['duplicate'] and before==await session.store.load() and rows==await session.rows(),'DUPLICATE_CLOSE_NOOP')
        checks['repeat_close_tick_noop']=True
        return await session.report(checks)
    finally:await session.cleanup()

async def run():
    if not __debug__:raise RuntimeError('HARNESS_REQUIRES_ASSERTIONS')
    cases=[]
    async def case(number,name,subcases):
        results=[]
        for label,side,kind,variant in subcases:
            try:
                value=await lifecycle('S'+str(number).zfill(2)+'_'+label,side,kind,variant);results.append(dict(label=label,**value))
            except Exception as exc:
                # Safe fixed code/type only; never exception text/connection strings.
                results.append(dict(label=label,status='FAIL',error_type=type(exc).__name__,test_only=True))
        cases.append(dict(id=number,name=name,status='PASS' if all(x['status']=='PASS' for x in results) else 'FAIL',subcases=results))
    with isolated():
        await case(1,'LONG → TAKE PROFIT',[('LONG_TP','LONG','TP',None)])
        await case(2,'LONG → STOP LOSS',[('LONG_SL','LONG','SL',None)])
        await case(3,'SHORT → TAKE PROFIT',[('SHORT_TP','SHORT','TP',None)])
        await case(4,'SHORT → STOP LOSS',[('SHORT_SL','SHORT','SL',None)])
        await case(5,'Simultaneous SL/TP; SL first',[(side+'_BOTH',side,'BOTH',None) for side in ('LONG','SHORT')])
        await case(6,'Fresh-process recovery with open position',[('RESTART','LONG','TP','restart')])
        await case(7,'Same candle in next scheduler slot',[('SAME_CANDLE','LONG','TP','same_candle')])
        await case(8,'Repeated real scheduler client via local ASGI',[('SCHEDULER','LONG','TP','scheduler')])
        await case(9,'Database failure after inserts/account update',[('ROLLBACK','LONG','TP','failure')])
        await case(10,'Recovery/retry after failed database transaction',[('RECOVERY','LONG','TP','recovery')])
        await case(11,'Competing controllers forced same revision',[('RACE','SHORT','SL','concurrent')])
        await case(12,'Independent math; adverse stop and conservative TP gaps',[(side+'_'+kind,side,kind,None) for side in ('LONG','SHORT') for kind in ('STOP_GAP','TP_GAP')])
    passed=all(x['status']=='PASS' for x in cases)
    report=dict(schema=SCHEMA,title='PAPER EXECUTION TECHNICAL VERIFICATION',technical_execution='PASS' if passed else 'FAIL',
        live_autonomous_execution='WAITING_FOR_REAL_SIGNAL',test_only=True,proves_live_autonomy=False,
        live_status_scope='PRODUCTION_NOT_OBSERVED; NO_LIVE_CYCLE_CAN_BE_VERIFIED_BY_HARNESS',code_hashes=code_hashes(),
        policy=POLICY,storage='FRESH_TEMPORARY_SQLITE_PRODUCTION_STORE_PER_SUBCASE',market='FIXED_SYNTHETIC_CONTEXT_ONLY_NO_REAL_SIGNALS',
        network='INET_CONNECT_AND_SUPABASE_CONSTRUCTION_FORBIDDEN',scenarios=cases,
        scenarios_passed=sum(x['status']=='PASS' for x in cases),scenarios_total=len(cases),
        production_supabase='NOT_ACCESSED; LIVE_RPC_ATOMICITY_NOT_TESTED',production_render='NOT_ACCESSED',
        actual_open_count=sum(x.get('actual_open_count',0) for c in cases for x in c['subcases']),
        actual_close_count=sum(x.get('actual_close_count',0) for c in cases for x in c['subcases']))
    report['checksum']=digest(report);return report

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--sandbox-poll',action='store_true');a=p.parse_args(argv)
    if a.output.name!='PAPER_EXECUTION_TECHNICAL_VERIFICATION.json' or a.output.is_symlink():p.error('fixed new report filename required')
    if a.output.exists():
        try:old=json.loads(a.output.read_bytes())
        except (ValueError,OSError):p.error('refusing to overwrite unrelated file')
        if old.get('schema')!=SCHEMA:p.error('refusing to overwrite unrelated report')
    if a.sandbox_poll:
        from scripts.replay_aura_csv import enable_sandbox_poll
        enable_sandbox_poll()
    value=asyncio.run(run());a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical(value))
    print(json.dumps(dict(technical_execution=value['technical_execution'],live_autonomous_execution=value['live_autonomous_execution'],scenarios_passed=value['scenarios_passed'],scenarios_total=value['scenarios_total'],actual_open_count=value['actual_open_count'],actual_close_count=value['actual_close_count'])))
    return 0 if value['technical_execution']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
