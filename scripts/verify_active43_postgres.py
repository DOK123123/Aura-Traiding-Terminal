"""Disposable real PostgreSQL plus production Active Service/Store/engine.

No production URL/DSN/env-key accepted. Fixed local Unix Docker socket, no network
or ports. Mock HTTP bridge calls REAL SQL RPCs; not hosted PostgREST/Render proof.
Synthetic fixtures and a separately recomputed natural historical signal are
explicitly isolated. Test events never reach a production portfolio.
"""
import argparse,asyncio,base64,hashlib,json,os,re,time,uuid
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import httpx
from app.active43.storage import Store
from app.active43.service import Service
from app.active43.core import initial,validate
from app.active43.strategies import config
from app.automated.storage import packed
from app.automated.engine import DemoError,initial as auto42_initial
from app.practice.core import seed as practice_seed
from scripts.verify_practice_postgres import docker,IMAGE
from scripts.verify_active43 import FixtureMarket
from scripts.verify_auto42_execution import check_accounting

ROOT=Path(__file__).resolve().parents[1];DATABASE='aura_active43_verification'

class PG:
    def __init__(self,name):
        if not re.fullmatch('aura-active43-pg-[a-f0-9]{12}',name):raise ValueError('Disposable Active43 container required')
        labels=json.loads(docker('inspect','--format','{{json .Config.Labels}}',name).stdout)
        mode=docker('inspect','--format','{{.HostConfig.NetworkMode}}',name).stdout.strip()
        if labels.get('aura.active43.verification')!='true' or mode!='none':raise ValueError('Isolation guard')
        self.name=name;self.clock=None
    def sql(self,sql,role='postgres',check=True):
        if role not in ('postgres','service_role','anon','authenticated'):raise ValueError('Role not allowed')
        r=docker('exec','-i',self.name,'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','postgres','-d',DATABASE,input='SET ROLE '+role+';\n'+sql,check=check)
        return r.stdout.strip() if check else r
    def rpc(self,name,args):
        expressions={
          'aura_active43_load':"a->'seed'",
          'aura_active43_commit':"(a->>'expected_revision')::bigint,a->'new_state',a->'new_events',a->>'operation_key'",
          'aura_active43_history':"a->>'selected_epoch',(a->>'after_seq')::bigint,(a->>'row_limit')::integer,a->>'event_id',a->>'kind_filter',(a->>'before_seq')::bigint"}
        if self.clock is not None:self.sql('UPDATE public.active43_test_clock SET epoch='+str(int(self.clock[0]))+';')
        encoded=base64.b64encode(json.dumps(args).encode()).decode()
        return json.loads(self.sql("WITH arg AS(SELECT convert_from(decode('"+encoded+"','base64'),'UTF8')::jsonb a) SELECT public."+name+'('+expressions[name]+') FROM arg;','service_role'))
    def ready(self):
        for _ in range(100):
            if docker('exec',self.name,'pg_isready','-h','127.0.0.1','-U','postgres','-d',DATABASE,check=False).returncode==0:return
            time.sleep(.1)
        raise RuntimeError('Local PostgreSQL not ready')
    def legacy_hash(self):
        sql="SELECT jsonb_build_object('auto42',(SELECT jsonb_agg(to_jsonb(t)) FROM public.aura_auto42_account t),'practice',(SELECT jsonb_agg(to_jsonb(t)) FROM public.aura_practice_account t),'auto_events',(SELECT count(*) FROM public.aura_auto42_events),'practice_events',(SELECT count(*) FROM public.aura_practice_events));"
        return hashlib.sha256(self.sql(sql).encode()).hexdigest()

class Bridge:
    def __init__(self,pg):self.pg=pg;self.lose_after_commit=False
    async def __call__(self,request):
        name=request.url.path.rsplit('/',1)[-1]
        if name not in ('aura_active43_load','aura_active43_commit','aura_active43_history'):raise AssertionError('Wrong portfolio RPC')
        try:value=await asyncio.to_thread(self.pg.rpc,name,json.loads(request.content))
        except Exception:return httpx.Response(503,json={'code':'OFFLINE_TEST_DB_FAILURE'})
        if name=='aura_active43_commit' and self.lose_after_commit:
            self.lose_after_commit=False;raise httpx.ReadTimeout('TEST_ONLY_UNKNOWN_COMMIT_OUTCOME')
        return httpx.Response(200,json=value)
    def store(self,cfg):return Store('https://abcdefghijkl.supabase.co','DUMMY_ACTIVE43_LOCAL_ONLY_'+'x'*40,cfg,httpx.MockTransport(self))

async def setup(pg,side='LONG',case='TP',tf='15m',strategy='DONCHIAN'):
    pg.sql('TRUNCATE public.aura_active43_account,public.aura_active43_events RESTART IDENTITY;')
    market=FixtureMarket(side,tf);now=[market.bars[-1].time+market.step+30];cfg=config(strategy,tf);pg.clock=now
    bridge=Bridge(pg);store=bridge.store(cfg);svc=Service(store,market,cfg,clock=lambda:now[0])
    env=await svc.load()
    with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,env['revision'])
    return market,now,bridge,store,svc

async def cycle(pg,side,kind,strategy='DONCHIAN'):
    market,now,bridge,store,svc=await setup(pg,side,kind,strategy=strategy)
    market.add();now[0]+=900;await svc.tick();assert (await store.load(now[0]))['state']['pending']
    market.add();now[0]+=900;other=Service(bridge.store(svc.config),market,svc.config,clock=lambda:now[0])
    await asyncio.gather(svc.tick(),other.tick());await other.close()
    p=deepcopy((await store.load(now[0]))['state']['position']);assert p
    cfg=svc.config;await svc.close();docker('restart',pg.name);pg.ready()
    store=bridge.store(cfg);svc=Service(store,market,cfg,clock=lambda:now[0]);assert (await svc.load())['state']['position']==p
    await svc.tick();market.signal=False;market.add(low='99.5',high='100.5');now[0]+=900;await svc.tick()
    assert (await svc.load())['state']['position']
    long=side=='LONG';tp=kind=='TP';both=kind=='BOTH'
    high='105' if both or long==tp else '101';low='95' if both or long!=tp else '99'
    if strategy=='TREND_ATR' and tp and not both:
        if long:low='99.5'
        else:high='100.5'
    market.add(high=high,low=low);now[0]+=900
    bridge.lose_after_commit=True
    try:await svc.tick()
    except DemoError as exc:assert exc.code=='STORAGE_TIMEOUT_OUTCOME_UNKNOWN'
    else:raise AssertionError('Unknown commit falsely confirmed')
    # Real SQL CLOSE was committed; retry reads the immutable key instead of
    # closing/charging twice, even though its prior HTTP reply was lost.
    await svc.tick();s=(await svc.load())['state'];validate(s)
    rows=await store.history(limit=200);opens=[e for e in rows if e['kind']=='OPEN'];closes=[e['payload'] for e in rows if e['kind']=='CLOSE']
    assert len(opens)==len(closes)==1 and s['position'] is None
    assert closes[0]['exit_reason']==('STOP_LOSS_AMBIGUOUS' if both else 'TAKE_PROFIT' if tp else 'STOP_LOSS')
    check_accounting(p,closes[0],s)
    assert not (await svc.dashboard())['production_paper_verified']
    await svc.close()
    return dict(scenario=side+'_'+kind+'_'+strategy,status='PASS',starting_balance='10000',open=p,close=closes[0],final_balance=s['balance'],fees=s['fees'],slippage=s['slippage'],open_count=1,close_count=1,restart_restored=True,update_saved=True,unknown_close_outcome_deduplicated=True)

async def natural(pg,folder,side):
    from bisect import bisect_left
    from scripts.active43_history import load,aggregate
    from app.active43.market import analyze
    from app.lab.models import digest
    folder=Path(folder);full=json.loads((folder/'15m-DONCHIAN-full-year.json').read_text())
    matches=[t for t in full['trades'] if t['direction']==side and t['exit_time']-t['entry_time']>=1800]
    if not matches:return dict(status='NOT_AVAILABLE',direction=side,reason='No natural closed trade with intermediate update')
    trade=matches[0];at=trade['signal_at'];bars=aggregate(load(folder/'btc-5m.csv'),900);times=[b.time for b in bars]
    class HistoricalMarket:
        async def close(self):pass
        def move(self,cut):
            self.at=cut;self.bars=bars[bisect_left(times,cut//86400*86400-1000*900):bisect_left(times,cut)]
        async def snapshot(self,cfg):
            d=analyze(self.bars,cfg);d['source_sha256']=digest([b.data() for b in self.bars]);return self.bars,d,self.at+30
    pg.sql('TRUNCATE public.aura_active43_account,public.aura_active43_events RESTART IDENTITY;')
    market=HistoricalMarket();market.move(at-900);now=[at-870];pg.clock=now;bridge=Bridge(pg);store=bridge.store(config());svc=Service(store,market,config(),clock=lambda:now[0])
    env=await svc.load()
    with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','c'*32,env['revision'])
    position=None
    for cut in range(at,min(at+900*576,trade['exit_time']+1800)+1,900):
        market.move(cut);now[0]=cut+30;await svc.tick();s=(await svc.load())['state']
        if cut==at:assert s['pending'] and s['pending']['direction']==trade['direction']
        if s['position'] and position is None:
            position=deepcopy(s['position']);await svc.close();svc=Service(bridge.store(config()),market,config(),clock=lambda:now[0])
        if s['trades']:
            closed=(await svc.store.history(kind='CLOSE',limit=1))[0]['payload'];assert position
            check_accounting(position,closed,s);assert not (await svc.dashboard())['production_paper_verified']
            await svc.close();return dict(status='PASS',scope='REAL_HISTORICAL_SIGNAL_LOCAL_POSTGRESQL_NOT_RENDER',open=position,close=closed,final_balance=s['balance'])
    await svc.close();raise AssertionError('Natural cycle did not complete')

async def verify(pg,folder=None):
    pg.sql('CREATE SCHEMA extensions; CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN BYPASSRLS; GRANT USAGE ON SCHEMA public,extensions TO anon,authenticated,service_role;')
    pg.sql((ROOT/'scripts/auto42_schema.sql').read_text());pg.sql((ROOT/'scripts/practice_schema.sql').read_text())
    for fn,state in [('aura_auto42_load',auto42_initial(int(time.time()))),('aura_practice_load',practice_seed(int(time.time())))]:
        encoded=base64.b64encode(json.dumps(packed(state)).encode()).decode()
        pg.sql("SELECT public."+fn+"(convert_from(decode('"+encoded+"','base64'),'UTF8')::jsonb);")
    before=pg.legacy_hash();sql=(ROOT/'scripts/active43_schema.sql').read_text();pg.sql(sql);pg.sql(sql)
    assert pg.legacy_hash()==before
    real_now=int(pg.sql('SELECT public.aura_active43_now();'));assert abs(real_now-int(time.time()))<5
    # Superuser-controlled clock ONLY in this disposable verification DB.
    # Production helper above is real clock_timestamp and not writable by service_role.
    pg.sql('CREATE TABLE public.active43_test_clock(epoch bigint); INSERT INTO public.active43_test_clock VALUES(0); CREATE OR REPLACE FUNCTION public.aura_active43_now() RETURNS bigint LANGUAGE sql VOLATILE SET search_path=public,pg_temp AS $$ SELECT epoch FROM public.active43_test_clock $$;')
    checks=['MIGRATION_REAPPLY_LEGACY_ACCOUNTS_UNCHANGED']
    for role in ('anon','authenticated'):
        for call in ("aura_active43_load('{}'::jsonb)","aura_active43_commit(1,'{}'::jsonb,'[]'::jsonb,'x')",'aura_active43_history(NULL,NULL,10,NULL,NULL,NULL)'):
            r=pg.sql('SELECT public.'+call+';',role,check=False);assert r.returncode and 'permission denied' in r.stderr
        for table in ('aura_active43_account','aura_active43_events'):
            r=pg.sql('SELECT * FROM public.'+table+';',role,check=False);assert r.returncode and 'permission denied' in r.stderr
    assert pg.sql("SELECT bool_and(relrowsecurity) FROM pg_class WHERE oid IN ('aura_active43_account'::regclass,'aura_active43_events'::regclass);")=='t'
    assert pg.rpc('aura_active43_load',dict(seed=packed(auto42_initial(int(time.time())))))['error']=='CORRUPT_PORTFOLIO'
    checks.append('RLS_ANON_AUTHENTICATED_DENIED_SERVICE_ROLE_ONLY_SCOPE_ENFORCED')
    cases=[]
    for side in ('LONG','SHORT'):
        for kind in ('TP','SL','BOTH'):
            value=await cycle(pg,side,kind);cases.append(value);print('POSTGRES_CASE',value['scenario'],'PASS',flush=True)
    cases.append(await cycle(pg,'LONG','TP',strategy='TREND_ATR'))
    market,now,bridge,store,svc=await setup(pg)
    market.signal=False;market.add(low='99.5',high='100.5');now[0]+=900;await svc.tick();assert (await svc.load())['state']['position'] is None
    checks.append('NO_SIGNAL_NO_ORDER')
    market.failure='MARKET_UNAVAILABLE';now[0]+=300;await svc.tick();assert (await svc.load())['state']['mode']=='PAUSED'
    market.failure=None;now[0]+=300;await svc.tick();assert (await svc.load())['state']['mode']=='ON'
    checks.append('SOURCE_OUTAGE_PAUSE_AND_RECOVERY')
    market.signal=True;market.add();now[0]+=900;await svc.tick();before_failure=await svc.load()
    market.add();now[0]+=900
    pg.clock=[now[0]+900]
    try:await svc.tick()
    except DemoError as exc:assert exc.code=='STALE_EXECUTION_AT_COMMIT'
    else:raise AssertionError('Stale OPEN committed at database boundary')
    pg.clock=now;assert await svc.load()==before_failure
    checks.append('DATABASE_CLOCK_BLOCKS_LATE_OPEN_AT_COMMIT')
    pg.sql("CREATE FUNCTION public.test_active43_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'OFFLINE_TEST_ONLY_FAILURE'; END $$; CREATE TRIGGER test_active43_fail BEFORE UPDATE ON public.aura_active43_account FOR EACH ROW EXECUTE FUNCTION public.test_active43_fail();")
    try:await svc.tick()
    except DemoError:pass
    else:raise AssertionError('Failed save confirmed OPEN')
    assert await svc.load()==before_failure
    assert not await store.history(kind='OPEN')
    pg.sql('DROP TRIGGER test_active43_fail ON public.aura_active43_account; DROP FUNCTION public.test_active43_fail();')
    bridge.lose_after_commit=True
    try:await svc.tick()
    except DemoError:pass
    else:raise AssertionError('Unknown OPEN outcome confirmed')
    await svc.tick();assert len(await store.history(kind='OPEN'))==1
    checks.append('SQL_FAILURE_ROLLBACK_AND_UNKNOWN_OPEN_OUTCOME_EXACTLY_ONCE')
    saved=await svc.load();docker('stop',pg.name);now[0]+=300
    try:await svc.tick()
    except DemoError:pass
    else:raise AssertionError('Stopped DB confirmed tick')
    docker('start',pg.name);pg.ready();assert await svc.load()==saved
    checks.append('REAL_DATABASE_OUTAGE_RESTART_STATE_RESTORED')
    await svc.close();actual=[await natural(pg,folder,side) for side in ('LONG','SHORT')] if folder else []
    assert pg.legacy_hash()==before;checks.append('LEGACY_AUTO42_PRACTICE_UNCHANGED_ENTIRE_RUN')
    return dict(checks=checks,cases=cases,natural_cycle=actual,legacy_before_sha256=before,legacy_after_sha256=pg.legacy_hash())


def run(output,folder=None):
    if not __debug__ or os.getenv('RENDER'):raise ValueError('LOCAL_ONLY_ASSERTIONS_REQUIRED')
    output=Path(output)
    if output.exists():raise ValueError('New output path required')
    if folder and not (Path(folder)/'15m-DONCHIAN-full-year.json').is_file():raise ValueError('HISTORICAL_REPORT_NOT_READY')
    name='aura-active43-pg-'+uuid.uuid4().hex[:12]
    docker('info','--format','{{.ServerVersion}}')
    docker('run','-d','--name',name,'--label','aura.active43.verification=true','--network','none','--memory','512m','--cpus','1','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB='+DATABASE,IMAGE,timeout=180)
    try:
        pg=PG(name);pg.ready();result=asyncio.run(verify(pg,folder))
        result.update(UNIT_TEST_PASSED=True,POSTGRESQL_VERIFIED=True,RLS_VERIFIED=True,TECHNICAL_EXECUTION='PASS',PRODUCTION_PAPER_VERIFIED=False,
            adapter='Mock HTTP bridge to actual local PostgreSQL production RPCs; not hosted PostgREST',postgres_version=pg.sql('SELECT version();'),image=IMAGE,
            synthetic_cases=True,production_access=False,real_orders=False,limits=dict(network='none',ports=0,memory='512 MiB',cpus=1))
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(output=str(output),cases=len(result['cases']),checks=len(result['checks']),natural=[r['status'] for r in result['natural_cycle']],TECHNICAL_EXECUTION='PASS')));return result
    finally:docker('rm','-fv',name,check=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--history-folder',type=Path)
    from scripts.replay_aura_csv import enable_sandbox_poll
    enable_sandbox_poll();a=p.parse_args();run(a.output,a.history_folder)
