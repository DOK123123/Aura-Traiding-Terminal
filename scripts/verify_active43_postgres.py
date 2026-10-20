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

ROOT=Path(__file__).resolve().parents[1];DATABASE='aura_active43_bitget_verification'

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
          'aura_active43_bitget_load':"a->'seed'",
          'aura_active43_bitget_commit':"(a->>'expected_revision')::bigint,a->'new_state',a->'new_events',a->>'operation_key'",
          'aura_active43_bitget_history':"a->>'selected_epoch',(a->>'after_seq')::bigint,(a->>'row_limit')::integer,a->>'event_id',a->>'kind_filter',(a->>'before_seq')::bigint"}
        if self.clock is not None:self.sql('UPDATE public.active43_test_clock SET epoch='+str(int(self.clock[0]))+';')
        encoded=base64.b64encode(json.dumps(args).encode()).decode()
        return json.loads(self.sql("WITH arg AS(SELECT convert_from(decode('"+encoded+"','base64'),'UTF8')::jsonb a) SELECT public."+name+'('+expressions[name]+') FROM arg;','service_role'))
    def ready(self):
        for _ in range(100):
            if docker('exec',self.name,'pg_isready','-h','127.0.0.1','-U','postgres','-d',DATABASE,check=False).returncode==0:return
            time.sleep(.1)
        raise RuntimeError('Local PostgreSQL not ready')
    def legacy_hash(self):
        sql="SELECT jsonb_build_object('auto42',(SELECT jsonb_agg(to_jsonb(t)) FROM public.aura_auto42_account t),'practice',(SELECT jsonb_agg(to_jsonb(t)) FROM public.aura_practice_account t),'auto_events',(SELECT count(*) FROM public.aura_auto42_events),'practice_events',(SELECT count(*) FROM public.aura_practice_events),'spot43',(SELECT jsonb_agg(to_jsonb(t)) FROM public.aura_active43_account t),'spot43_events',(SELECT count(*) FROM public.aura_active43_events),'bybit43',(SELECT jsonb_agg(to_jsonb(t)) FROM public.aura_active43_bybit_account t),'bybit43_events',(SELECT count(*) FROM public.aura_active43_bybit_events));"
        return hashlib.sha256(self.sql(sql).encode()).hexdigest()

    def legacy_functions_hash(self):
        query="""SELECT coalesce(jsonb_agg(pg_get_functiondef(p.oid) ORDER BY p.proname,p.oid),'[]'::jsonb)
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND (p.proname LIKE 'aura_auto42_%' OR p.proname LIKE 'aura_practice_%'
          OR p.proname LIKE 'aura_active43_bybit_%' OR p.proname IN ('aura_active43_load','aura_active43_commit','aura_active43_history','aura_active43_now','aura_active43_immutable'));"""
        return hashlib.sha256(self.sql(query).encode()).hexdigest()

class Bridge:
    def __init__(self,pg):self.pg=pg;self.lose_after_commit=False
    async def __call__(self,request):
        name=request.url.path.rsplit('/',1)[-1]
        if request.method=='GET':
            assert name=='aura_active43_bitget_account'
            assert dict(request.url.params)=={'id':'eq.1','select':'revision,payload,sha256,saved_at','limit':'1'}
            query="SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) FROM (SELECT revision,payload,sha256,saved_at FROM public.aura_active43_bitget_account WHERE id=1 LIMIT 1) t;"
            try:value=json.loads(await asyncio.to_thread(self.pg.sql,query,'service_role'))
            except Exception:return httpx.Response(503,json={'code':'OFFLINE_TEST_DB_FAILURE'})
            return httpx.Response(200,json=value)
        assert request.method=='POST'
        if name not in ('aura_active43_bitget_load','aura_active43_bitget_commit','aura_active43_bitget_history'):raise AssertionError('Wrong portfolio RPC')
        try:value=await asyncio.to_thread(self.pg.rpc,name,json.loads(request.content))
        except Exception:return httpx.Response(503,json={'code':'OFFLINE_TEST_DB_FAILURE'})
        if name=='aura_active43_bitget_commit' and self.lose_after_commit:
            self.lose_after_commit=False;raise httpx.ReadTimeout('TEST_ONLY_UNKNOWN_COMMIT_OUTCOME')
        return httpx.Response(200,json=value)
    def store(self,cfg):return Store('https://abcdefghijkl.supabase.co','DUMMY_ACTIVE43_LOCAL_ONLY_'+'x'*40,cfg,httpx.MockTransport(self))

async def setup(pg,side='LONG',case='TP',tf='15m',strategy='DONCHIAN'):
    pg.sql('TRUNCATE public.aura_active43_bitget_account,public.aura_active43_bitget_events RESTART IDENTITY;')
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

async def public_cycle(pg,side):
    """Native Bitget V2 Market -> indicators -> actual SQL -> owner HTTP status.

    All market fixtures are synthetic/offline. Neither SQL nor the status can
    qualify as a natural Render cycle; no artificial production signal exists.
    """
    from fastapi import FastAPI
    from app.active43.api import router
    from app.active43.market import Market,Quotes
    from scripts.verify_active43 import PublicFixture
    pg.sql('TRUNCATE public.aura_active43_bitget_account,public.aura_active43_bitget_events RESTART IDENTITY;')
    f=PublicFixture(side);clock=lambda:f.now[0];pg.clock=f.now;bridge=Bridge(pg)
    transport=httpx.MockTransport(f.handler)
    market=Market(clock=clock,transport=transport);quotes=Quotes(clock=clock,transport=transport)
    svc=Service(bridge.store(config()),market,config(),clock=clock,quotes=quotes)
    app=FastAPI();app.include_router(router)
    async def external_tick():
        app.state.active43=svc
        token='DUMMY_BITGET_EXTERNAL_SCHEDULER_'+'x'*40
        with patch.dict('os.environ',AURA_ACTIVE43_BITGET_SCHEDULER_SECRET=token):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                r=await client.post('/api/active43/tick',headers={'X-Aura-Active43-Bitget-Token':token})
                assert r.status_code==200 and r.json()['state_saved'] is True
                return r.json()
    env=await svc.load()
    with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','c'*32,env['revision'])
    f.add('signal');await external_tick();assert (await svc.load())['state']['pending']['direction']==side
    f.add('fill');await external_tick();opened=deepcopy((await svc.load())['state']['position']);assert opened
    # New process/controller uses the database account, not browser state.
    await svc.close()
    market=Market(clock=clock,transport=transport);quotes=Quotes(clock=clock,transport=transport)
    svc=Service(bridge.store(config()),market,config(),clock=clock,quotes=quotes)
    assert (await svc.load())['state']['position']==opened
    f.add('update');await external_tick();assert (await svc.load())['state']['position']
    f.add('close');await external_tick();await external_tick()
    state=(await svc.load())['state'];closed=(await svc.store.history(kind='CLOSE'))[0]['payload']
    assert closed['exit_reason']=='TAKE_PROFIT' and state['trades']==1
    assert len(await svc.store.history(kind='OPEN'))==len(await svc.store.history(kind='CLOSE'))==1
    check_accounting(opened,closed,state)
    app.state.active43=svc
    with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_ACTIVE43_OWNER_ONLY'):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',auth=('aura','DUMMY_ACTIVE43_OWNER_ONLY')) as client:
            response=await client.get('/api/active43/status');body=response.json()
            assert response.status_code==200 and body['state']['balance']==state['balance']
            assert body['trades'][0]['id']==closed['id'] and body['chart']['source']==state['market_source']
            assert body['production_paper_verified'] is False
    await svc.close()
    return dict(status='PASS',direction=side,scope='OFFLINE_BITGET_V2_FIXTURES_NATIVE_INDICATORS_REAL_LOCAL_POSTGRESQL_OWNER_HTTP_NOT_RENDER',
                open=opened,close=closed,final_balance=state['balance'],open_count=1,close_count=1,restart_restored=True,external_scheduler_http=True,no_browser=True)


async def account_preparation(pg):
    """Native public protocol fixture -> setup HTTP -> real SQL -> restart/readback."""
    from fastapi import FastAPI
    from app.active43.api import router
    from app.active43.market import Market
    from scripts.verify_active43 import PublicFixture
    from tests.test_active43_diagnostics import diagnostic_transport
    pg.sql('TRUNCATE public.aura_active43_bitget_account,public.aura_active43_bitget_events RESTART IDENTITY;')
    f=PublicFixture();clock=lambda:f.now[0];bridge=Bridge(pg);cfg=config()
    a=Service(bridge.store(cfg),clock=clock);b=Service(bridge.store(cfg),clock=clock)
    factory=lambda **kw:Market(clock=kw['clock'],transport=diagnostic_transport(f))
    token='DUMMY_ISOLATED_INIT_TOKEN_'+'x'*40
    app=FastAPI();app.include_router(router);app.state.active43=a
    hdr={'X-Aura-Active43-Bitget-Token':token};body={'confirmation':'INITIALIZE ISOLATED PAPER ACCOUNT'}
    with patch.dict(os.environ,AURA_ACTIVE43_BITGET_SCHEDULER_SECRET=token,AURA_ACTIVE43_BITGET_ENABLED='true',AURA_ACTIVE43_ENABLED='true'),patch('app.active43.diagnostics.Market',side_effect=factory):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            reports=await asyncio.gather(c.post('/api/active43/initialize',headers=hdr,json=body),b.initialize())
            assert reports[0].status_code==200 and reports[1]['readback_verified']
            assert pg.sql('SELECT count(*) FROM public.aura_active43_bitget_account;')=='1'
            saved=await a.store.peek();assert saved['state']['balance']=='10000' and saved['state']['mode']=='OFF' and saved['state']['position'] is None
            assert await a.store.history(limit=10)==[]
            responses=await asyncio.gather(*[c.post('/api/active43/verify-off-tick',headers=hdr,json=body) for _ in range(2)])
            assert all(r.status_code==200 and r.json()['mode']=='OFF' and r.json()['opened']==r.json()['closed']==0 for r in responses)
            rows=await a.store.history(limit=10);assert [r['kind'] for r in rows]==['TICK']
            result=(await c.post('/api/active43/diagnostics/scheduler',headers=hdr)).json()
            assert result['scheduler']['status']=='ACTIVE' and result['mode']=='OFF' and not result['production_paper_verified']
        saved=await a.store.peek();await a.close();await b.close()
        docker('restart',pg.name);pg.ready()
        restored=Service(bridge.store(cfg),clock=clock)
        assert await restored.store.peek()==saved
        assert (await restored.initialize())['balance']=='10000'
        assert await restored.store.peek()==saved
        assert all(e['kind']=='TICK' for e in await restored.store.history(limit=10))
        await restored.close()
    return dict(status='PASS',scope='ISOLATED_LOCAL_POSTGRES_AND_SYNTHETIC_MARKET_NOT_RENDER',
        concurrent_initialization=True,single_account=True,restart_restored=True,reinitialization_unchanged=True,
        balance='10000',mode='OFF',open_count=0,close_count=0,tick_count=1,postflight_scheduler='ACTIVE',production_paper_verified=False)


async def verify(pg):
    pg.sql('CREATE SCHEMA extensions; CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN BYPASSRLS; GRANT USAGE ON SCHEMA public,extensions TO anon,authenticated,service_role;')
    pg.sql((ROOT/'scripts/auto42_schema.sql').read_text());pg.sql((ROOT/'scripts/practice_schema.sql').read_text())
    for fn,state in [('aura_auto42_load',auto42_initial(int(time.time()))),('aura_practice_load',practice_seed(int(time.time())))]:
        encoded=base64.b64encode(json.dumps(packed(state)).encode()).decode()
        pg.sql("SELECT public."+fn+"(convert_from(decode('"+encoded+"','base64'),'UTF8')::jsonb);")
    pg.sql((ROOT/'scripts/active43_schema.sql').read_text())
    archived=dict(auto42_initial(int(time.time())),scope='AURA43_ACTIVE_PAPER',strategy_version='AURA_4.3_ACTIVE_PAPER_1',epoch='ACTIVE43_ARCHIVED_SPOT_ACCOUNT')
    encoded=base64.b64encode(json.dumps(packed(archived)).encode()).decode()
    pg.sql("SELECT public.aura_active43_load(convert_from(decode('"+encoded+"','base64'),'UTF8')::jsonb);")
    pg.sql((ROOT/'scripts/active43_bybit_schema.sql').read_text())
    bybit=dict(auto42_initial(int(time.time())),scope='AURA43_ACTIVE_PAPER',strategy_version='AURA_4.3_ACTIVE_PAPER_2',epoch='ACTIVE43_BYBIT_ARCHIVED',
        market_source='Bybit · USDT Perpetual / api.bybit.com',market_identity=dict(exchange='BYBIT',market_type='USDT_PERPETUAL',category='linear',symbol='BTCUSDT',settlement='USDT'))
    encoded=base64.b64encode(json.dumps(packed(bybit)).encode()).decode()
    pg.sql("SELECT public.aura_active43_bybit_load(convert_from(decode('"+encoded+"','base64'),'UTF8')::jsonb);")
    before_functions=pg.legacy_functions_hash()
    before=pg.legacy_hash();sql=(ROOT/'scripts/active43_bitget_schema.sql').read_text();pg.sql(sql);pg.sql(sql)
    grant=(ROOT/'scripts/active43_bitget_diagnostics_grant.sql').read_text();pg.sql(grant);pg.sql(grant)
    assert pg.legacy_hash()==before and pg.legacy_functions_hash()==before_functions
    real_now=int(pg.sql('SELECT public.aura_active43_bitget_now();'));assert abs(real_now-int(time.time()))<5
    # Superuser-controlled clock ONLY in this disposable verification DB.
    # Production helper above is real clock_timestamp and not writable by service_role.
    pg.sql('CREATE TABLE public.active43_test_clock(epoch bigint); INSERT INTO public.active43_test_clock VALUES(0); CREATE OR REPLACE FUNCTION public.aura_active43_bitget_now() RETURNS bigint LANGUAGE sql VOLATILE SET search_path=public,pg_temp AS $$ SELECT epoch FROM public.active43_test_clock $$;')
    checks=['MIGRATION_REAPPLY_LEGACY_ACCOUNTS_UNCHANGED']
    for role in ('anon','authenticated'):
        for call in ("aura_active43_bitget_load('{}'::jsonb)","aura_active43_bitget_commit(1,'{}'::jsonb,'[]'::jsonb,'x')",'aura_active43_bitget_history(NULL,NULL,10,NULL,NULL,NULL)'):
            r=pg.sql('SELECT public.'+call+';',role,check=False);assert r.returncode and 'permission denied' in r.stderr
        for table in ('aura_active43_bitget_account','aura_active43_bitget_events'):
            r=pg.sql('SELECT * FROM public.'+table+';',role,check=False);assert r.returncode and 'permission denied' in r.stderr
    assert pg.sql("SELECT bool_and(relrowsecurity) FROM pg_class WHERE oid IN ('aura_active43_bitget_account'::regclass,'aura_active43_bitget_events'::regclass);")=='t'
    assert pg.rpc('aura_active43_bitget_load',dict(seed=packed(auto42_initial(int(time.time())))))['error']=='CORRUPT_PORTFOLIO'
    checks.append('RLS_ANON_AUTHENTICATED_DENIED_SERVICE_ROLE_ONLY_SCOPE_ENFORCED')
    assert pg.sql('SELECT count(*) FROM public.aura_active43_bitget_account;','service_role')=='0'
    for privilege in ('INSERT','UPDATE','DELETE'):
        assert pg.sql("SELECT has_table_privilege('service_role','public.aura_active43_bitget_account','"+privilege+"');")=='f'
    empty=Bridge(pg).store(config())
    assert await empty.peek() is None
    assert pg.sql('SELECT count(*) FROM public.aura_active43_bitget_account;')=='0'
    await empty.close()
    checks.append('READ_ONLY_PEEK_DOES_NOT_INITIALIZE_AND_GRANTS_NO_TABLE_WRITES')
    preparation=await account_preparation(pg)
    checks.append('ACCOUNT_PREPARATION_CONCURRENT_HTTP_INIT_OFF_HEARTBEAT_AND_DATABASE_RESTART')
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
    pg.sql("CREATE FUNCTION public.test_active43_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'OFFLINE_TEST_ONLY_FAILURE'; END $$; CREATE TRIGGER test_active43_fail BEFORE UPDATE ON public.aura_active43_bitget_account FOR EACH ROW EXECUTE FUNCTION public.test_active43_fail();")
    try:await svc.tick()
    except DemoError:pass
    else:raise AssertionError('Failed save confirmed OPEN')
    assert await svc.load()==before_failure
    assert not await store.history(kind='OPEN')
    pg.sql('DROP TRIGGER test_active43_fail ON public.aura_active43_bitget_account; DROP FUNCTION public.test_active43_fail();')
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
    assert await store.peek()==saved
    ledger_before=pg.sql("SELECT jsonb_build_object('account',(SELECT jsonb_agg(to_jsonb(t)) FROM public.aura_active43_bitget_account t),'events',(SELECT jsonb_agg(to_jsonb(t)) FROM public.aura_active43_bitget_events t));")
    async def skip_market(report):report['bitget']={'status':'ERROR','code':'OFFLINE_TEST_ONLY'}
    with patch.object(svc.diagnostics,'market_probe',side_effect=skip_market):
        diagnostic=await svc.diagnostics.run(scheduler_delivery=True)
    assert diagnostic['supabase']['status']=='CONNECTED' and diagnostic['state_changed'] is False
    assert diagnostic['virtual_balance']==saved['state']['balance']
    assert ledger_before==pg.sql("SELECT jsonb_build_object('account',(SELECT jsonb_agg(to_jsonb(t)) FROM public.aura_active43_bitget_account t),'events',(SELECT jsonb_agg(to_jsonb(t)) FROM public.aura_active43_bitget_events t));")
    checks.append('DIAGNOSTIC_ON_OPEN_POSITION_BYTE_IDENTICAL_LEDGER_AFTER_RESTART')
    await svc.close();actual=[await public_cycle(pg,side) for side in ('LONG','SHORT')]
    assert pg.legacy_hash()==before;checks.append('LEGACY_AUTO42_PRACTICE_SPOT43_BYBIT43_UNCHANGED_ENTIRE_RUN')
    assert pg.legacy_functions_hash()==before_functions
    checks.append('LEGACY_SQL_FUNCTION_DEFINITIONS_UNCHANGED')
    return dict(checks=checks,cases=cases,native_cycles=actual,preparation=preparation,legacy_before_sha256=before,legacy_after_sha256=pg.legacy_hash(),legacy_functions_before_sha256=before_functions,legacy_functions_after_sha256=pg.legacy_functions_hash())


def run(output):
    if not __debug__ or os.getenv('RENDER'):raise ValueError('LOCAL_ONLY_ASSERTIONS_REQUIRED')
    output=Path(output)
    if output.exists():raise ValueError('New output path required')
    name='aura-active43-pg-'+uuid.uuid4().hex[:12]
    docker('info','--format','{{.ServerVersion}}')
    docker('run','-d','--name',name,'--label','aura.active43.verification=true','--network','none','--memory','512m','--cpus','1','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB='+DATABASE,IMAGE,timeout=180)
    try:
        pg=PG(name);pg.ready();result=asyncio.run(verify(pg))
        result.update(UNIT_TEST_PASSED=True,POSTGRESQL_VERIFIED=True,RLS_VERIFIED=True,TECHNICAL_EXECUTION='PASS',PRODUCTION_PAPER_VERIFIED=False,
            adapter='Mock HTTP bridge to actual local PostgreSQL production RPCs; not hosted PostgREST',postgres_version=pg.sql('SELECT version();'),image=IMAGE,
            synthetic_cases=True,production_access=False,real_orders=False,limits=dict(network='none',ports=0,memory='512 MiB',cpus=1))
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(output=str(output),cases=len(result['cases']),checks=len(result['checks']),native_cycles=[r['status'] for r in result['native_cycles']],TECHNICAL_EXECUTION='PASS')));return result
    finally:docker('rm','-fv',name,check=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    from scripts.replay_aura_csv import enable_sandbox_poll
    enable_sandbox_poll();a=p.parse_args();run(a.output)
