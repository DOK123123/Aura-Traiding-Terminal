"""Local-only Auto42 Service -> production engine -> real PostgreSQL RPC tests.

No DSN, URL, Supabase credentials or production configuration accepted. psql
replaces HTTP transport only; production store validation/transactions are real.
Synthetic fixtures prove technical behavior, never natural/live signal evidence.
"""
import argparse
import asyncio
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import time
import uuid
from unittest.mock import patch

from app.automated.engine import initial,event,DemoError
from app.automated.service import Service
from app.automated.storage import SupabaseStore,packed
from scripts.verify_auto42_execution import TestMarket,check_accounting
from scripts.verify_practice_postgres import docker,IMAGE

ROOT=Path(__file__).resolve().parents[1]
DATABASE='aura_auto42_verification'


class LocalPG:
    def __init__(self,name):
        if not re.fullmatch('aura-auto42-pg-[a-f0-9]{12}',name):raise ValueError('Disposable local container required')
        labels=json.loads(docker('inspect','--format','{{json .Config.Labels}}',name).stdout)
        network=docker('inspect','--format','{{.HostConfig.NetworkMode}}',name).stdout.strip()
        if labels.get('aura.auto42.verification')!='true' or network!='none':raise ValueError('Isolation guard failed')
        self.name=name
    def sql(self,sql,role='postgres',check=True):
        if role not in ('postgres','service_role','anon','authenticated'):raise ValueError('Test role required')
        result=docker('exec','-i',self.name,'psql','-X','-qAt','-v','ON_ERROR_STOP=1',
            '-U','postgres','-d',DATABASE,input='SET ROLE '+role+';\n'+sql,check=check)
        return result.stdout.strip() if check else result
    def rpc(self,name,args):
        expressions={
            'aura_auto42_load':"a->'seed'",
            'aura_auto42_commit':"(a->>'expected_revision')::bigint,a->'new_state',a->'new_events',a->>'operation_key'",
            'aura_auto42_history':"a->>'selected_epoch',(a->>'after_seq')::bigint,(a->>'row_limit')::integer,a->>'event_id'",
            'aura_auto42_closed_trades':"a->>'selected_epoch',(a->>'before_seq')::bigint,(a->>'row_limit')::integer"}
        encoded=base64.b64encode(json.dumps(args).encode()).decode()
        sql="WITH arg AS (SELECT convert_from(decode('"+encoded+"','base64'),'UTF8')::jsonb a) SELECT public."+name+'('+expressions[name]+') FROM arg;'
        return json.loads(self.sql(sql,'service_role'))
    def ready(self):
        for _ in range(100):
            if docker('exec',self.name,'pg_isready','-h','127.0.0.1','-U','postgres','-d',DATABASE,check=False).returncode==0:return
            time.sleep(.1)
        raise RuntimeError('Disposable PostgreSQL startup failed')


class PostgreSQLStore(SupabaseStore):
    def __init__(self,pg):self.pg=pg;self.diagnostics={}
    async def rpc(self,name,args):
        value=await asyncio.to_thread(self.pg.rpc,name,args)
        if isinstance(value,dict) and value.get('error'):raise DemoError(value['error'])
        return value
    async def close(self):pass


async def setup(pg,side,case):
    pg.sql('TRUNCATE public.aura_auto42_events,public.aura_auto42_account RESTART IDENTITY;')
    market=TestMarket(side);now=[market.bars[-1].time+930];store=PostgreSQLStore(pg)
    await store.rpc('aura_auto42_load',dict(seed=packed(initial(now[0],epoch='TEST_ONLY_'+side+'_'+case))))
    service=Service(market,store,clock=lambda:now[0])
    with patch('app.automated.service.scheduler_configured',return_value=True):await service.control('START','a'*32)
    return market,now,store,service


async def cycle(pg,side,kind):
    market,now,store,svc=await setup(pg,side,kind)
    market.add();now[0]+=900;await svc.tick()
    assert (await store.load())['state']['pending']
    market.add();now[0]+=900
    # Independent controller instances race against the same PostgreSQL CAS.
    other=Service(market,PostgreSQLStore(pg),clock=lambda:now[0])
    await asyncio.gather(svc.tick(),other.tick());await other.close()
    position=deepcopy((await store.load())['state']['position']);assert position
    await svc.close()
    docker('restart',pg.name);pg.ready()
    store=PostgreSQLStore(pg);svc=Service(market,store,clock=lambda:now[0])
    assert (await store.load())['state']['position']==position
    await svc.tick();market.signal=False
    # First a real engine mark with no exit; then deterministic SL/TP touches.
    market.add();now[0]+=900;await svc.tick()
    assert (await store.load())['state']['position']==position
    long=side=='LONG';tp=kind=='TP';both=kind=='BOTH'
    high='105' if both or long==tp else '101'
    low='95' if both or long!=tp else '99'
    market.add(h=high,l=low);now[0]+=900;await svc.tick();await svc.tick()
    env=await store.load();s=env['state'];rows=await store.history(limit=200)
    opens=[e for e in rows if e['kind']=='OPEN'];closes=[e['payload'] for e in rows if e['kind']=='CLOSE']
    assert len(opens)==len(closes)==1 and s['position'] is None and s['trades']==1
    expected='STOP_LOSS_AMBIGUOUS' if both else 'TAKE_PROFIT' if tp else 'STOP_LOSS'
    assert closes[0]['exit_reason']==expected
    check_accounting(position,closes[0],s)
    history=await store.closed_trades(s['epoch']);assert len(history)==1
    assert await store.closed_trades(s['epoch'],before=history[0]['seq'])==[]
    assert await store.closed_trades('different-epoch')==[]
    assert not (await svc.live_monitor())['live_cycle_verified']
    await svc.close()
    return dict(status='PASS',scenario=side+'_'+kind,starting_balance='10000',position=position,
        close=closes[0],ending_balance=s['balance'],fees=s['fees'],slippage=s['slippage'],
        opened=1,closed=1,restart_restored=True,concurrent_and_repeated_tick_deduplicated=True,
        position_update_persisted=True,math='INDEPENDENT_DECIMAL_ORACLE')


async def natural_cycle(pg,csv,signal_at):
    """Recompute real, causal production snapshots, not supplied test signals."""
    from bisect import bisect_left
    from app.lab.local_csv import load_binance_csv
    from app.lab.models import digest
    from scripts.replay_auto42_verification import PrefixCache,snapshot
    bars,identity=load_binance_csv(csv);times=[b.time for b in bars]
    class HistoricalMarket:
        def __init__(self):self.bars=[];self.value=None;self.group=None
        def at(self,at):
            boundary=at//14400*14400
            if self.group!=boundary:
                self.group=boundary;start=boundary-4160*900
                self.begin=bisect_left(times,start)
                self.cache=PrefixCache(bars[self.begin:bisect_left(times,boundary+14400)])
            self.bars=bars[self.begin:bisect_left(times,at)]
            with self.cache.installed():self.value=snapshot(self.bars,at)
        async def snapshot(self,tf):return deepcopy(self.value)
    market=HistoricalMarket();market.at(signal_at-900);now=[signal_at-900+30]
    pg.sql('TRUNCATE public.aura_auto42_events,public.aura_auto42_account RESTART IDENTITY;')
    store=PostgreSQLStore(pg)
    await store.rpc('aura_auto42_load',dict(seed=packed(initial(now[0],epoch='TEST_ONLY_REAL_HISTORY'))))
    svc=Service(market,store,clock=lambda:now[0])
    with patch('app.automated.service.scheduler_configured',return_value=True):await svc.control('START','b'*32)
    position=None
    try:
        # No future decision/price enters a snapshot. A complete 90-day source
        # can contain more data; the current production rolling prefix is used.
        for at in range(signal_at,min(signal_at+576*900,times[-1]+900)+1,900):
            market.at(at);now[0]=at+30;await svc.tick()
            s=(await store.load())['state']
            if at==signal_at:
                assert s['pending'] and s['pending']['reason']=='CONFIRMED_STRUCTURE_RETEST'
            if s['position'] and position is None:
                position=deepcopy(s['position'])
                await svc.close();svc=Service(market,PostgreSQLStore(pg),clock=lambda:now[0])
                assert (await svc.store.load())['state']['position']==position
            if s['trades']:
                rows=await store.closed_trades(s['epoch']);assert len(rows)==1 and position
                close=rows[0]['payload'];check_accounting(position,close,s)
                assert not (await svc.live_monitor())['live_cycle_verified']
                return dict(status='PASS',evidence_type='REAL_HISTORICAL_SIGNAL_LOCAL_POSTGRESQL_NOT_RENDER',
                    source_sha256=identity['sha256'],signal_at=signal_at,position=position,close=close,
                    final_balance=s['balance'],fees=s['fees'],slippage=s['slippage'],
                    restart_restored=True,live_cycle_verified=False)
        raise AssertionError('Natural signal did not complete within bounded historical window')
    finally:await svc.close()


async def verify(pg,history=None,signal_at=None):
    pg.sql('CREATE SCHEMA extensions; CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; '
           'CREATE ROLE service_role NOLOGIN BYPASSRLS; GRANT USAGE ON SCHEMA public,extensions TO anon,authenticated,service_role;')
    for path in ('scripts/auto42_schema.sql','scripts/auto42_trade_history.sql'):
        pg.sql((ROOT/path).read_text());pg.sql((ROOT/path).read_text())
    checks=['SCHEMA_APPLY_REAPPLY']
    for role in ('anon','authenticated'):
        for call in ('aura_auto42_load(\'{}\'::jsonb)','aura_auto42_commit(1,\'{}\'::jsonb,\'[]\'::jsonb,\'x\')',
                     'aura_auto42_history(NULL,NULL,10,NULL)',"aura_auto42_closed_trades('x',NULL,10)"):
            result=pg.sql('SELECT public.'+call+';',role,check=False)
            assert result.returncode and 'permission denied' in result.stderr
    assert pg.sql("SELECT bool_and(relrowsecurity) FROM pg_class WHERE oid IN ('aura_auto42_account'::regclass,'aura_auto42_events'::regclass);")=='t'
    checks.append('RLS_BROWSER_ROLES_DENIED_SERVICE_ROLE_RPC')
    cases=[]
    for side in ('LONG','SHORT'):
        for kind in ('TP','SL','BOTH'):cases.append(await cycle(pg,side,kind))
    market,now,store,svc=await setup(pg,'LONG','FAILURES')
    market.signal=False;market.add();now[0]+=900;await svc.tick()
    assert (await store.load())['state']['position'] is None
    checks.append('NO_SIGNAL_NO_ORDER')
    market.failure='STALE_DATA';now[0]+=300;await svc.tick()
    assert (await store.load())['state']['mode']=='PAUSED'
    checks.append('STALE_DATA_SAFE_PAUSE')
    market.failure=None;now[0]+=300;await svc.tick()
    assert (await store.load())['state']['mode']=='ON'
    checks.append('FRESH_DATA_RECOVERY')
    market.signal=True;market.add();now[0]+=900;await svc.tick()
    before=await store.load();assert before['state']['pending']
    market.add();now[0]+=900
    # Real SQL failure after events have been inserted but before account update.
    pg.sql("CREATE FUNCTION public.auto42_test_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'TEST_ONLY_WRITE_FAILURE'; END $$; "
           'CREATE TRIGGER auto42_test_failure BEFORE UPDATE ON public.aura_auto42_account FOR EACH ROW EXECUTE FUNCTION public.auto42_test_failure();')
    try:await svc.tick()
    except Exception as exc:
        import subprocess
        assert isinstance(exc,subprocess.CalledProcessError)
    else:raise AssertionError('Failed DB write falsely confirmed')
    assert await store.load()==before
    assert not [e for e in await store.history(limit=200) if e['kind']=='OPEN']
    pg.sql('DROP TRIGGER auto42_test_failure ON public.aura_auto42_account; DROP FUNCTION public.auto42_test_failure();')
    checks.append('SQL_FAILURE_ROLLS_BACK_ACCOUNT_EVENTS_AND_TICK_KEY')
    await svc.tick();assert (await store.load())['state']['position']
    assert len([e for e in await store.history(limit=200) if e['kind']=='OPEN'])==1
    checks.append('RETRY_AFTER_FAILED_COMMIT_OPENS_EXACTLY_ONCE')
    # A real stopped database cannot confirm any further state transition.
    saved=await store.load();docker('stop',pg.name);now[0]+=300
    try:await svc.tick()
    except Exception:pass
    else:raise AssertionError('Unavailable PostgreSQL falsely confirmed')
    docker('start',pg.name);pg.ready()
    assert await store.load()==saved
    checks.append('DATABASE_UNAVAILABLE_NO_CONFIRMED_ORDER_RESTART_RECOVERS')
    await svc.close()
    natural=await natural_cycle(pg,history,signal_at) if history is not None else None
    return dict(checks=checks,cases=cases,natural_historical_cycle=natural)


def run(output,history=None,signal_at=None):
    if not __debug__ or os.getenv('RENDER'):raise ValueError('Local verification only, assertions required')
    output=Path(output)
    if output.exists():raise ValueError('Use a new output path')
    if (history is None)!=(signal_at is None):raise ValueError('History and historical cutoff required together')
    name='aura-auto42-pg-'+uuid.uuid4().hex[:12]
    docker('info','--format','{{.ServerVersion}}')
    docker('run','-d','--name',name,'--label','aura.auto42.verification=true','--network','none',
        '--memory','512m','--cpus','1','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB='+DATABASE,IMAGE,timeout=180)
    try:
        pg=LocalPG(name);pg.ready();result=asyncio.run(verify(pg,history,signal_at))
        result.update(TECHNICAL_EXECUTION='PASS',POSTGRESQL_VERIFIED=True,RLS_VERIFIED=True,
            LIVE_AUTONOMOUS_EXECUTION='WAITING_FOR_REAL_SIGNAL',PRODUCTION_VERIFIED=False,
            adapter='REAL_LOCAL_POSTGRESQL_SQL_RPC_NOT_HTTP_POSTGREST',
            market='TEST_ONLY_SYNTHETIC_CONTEXT_NOT_NATURAL_SIGNAL_EVIDENCE',
            postgres_version=pg.sql('SELECT version();'),docker_image=IMAGE,
            isolation=dict(network='none',published_ports=0,memory='512 MiB',cpus=1),
            production_access=False,real_orders=False)
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
        print(json.dumps(dict(output=str(output),checks=len(result['checks']),cases=len(result['cases']),TECHNICAL_EXECUTION='PASS')))
        return result
    finally:docker('rm','-fv',name,check=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--history',type=Path);p.add_argument('--signal-at',type=int)
    from scripts.replay_aura_csv import enable_sandbox_poll
    enable_sandbox_poll();args=p.parse_args();run(args.output,args.history,args.signal_at)
