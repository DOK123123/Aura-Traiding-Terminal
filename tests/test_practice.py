"""Offline Paper Practice integration; fake quotes/SQLite-backed RPC, NOT live Supabase."""
import asyncio
from copy import deepcopy
from decimal import Decimal as D,localcontext,ROUND_CEILING,ROUND_HALF_EVEN
import json
from pathlib import Path
import sqlite3
import uuid
from unittest.mock import patch
import httpx
import pytest
from fastapi import FastAPI
from app.practice.core import SOURCE,seed,checked,transition
from app.practice.market import Quotes
from app.practice.storage import Store
from app.practice.service import Service
from app.practice.api import router
from app.automated.engine import DemoError
from app.automated.storage import unpack

NOW=1800000000

def quote(price='100',trade=1):return dict(price=price,time_ms=NOW*1000,trade_id=trade,source=SOURCE)
def command(side='LONG'):
    return dict(request_id=str(uuid.uuid4()),direction=side,stop_loss='98' if side=='LONG' else '102',take_profit='104' if side=='LONG' else '96',expected_price='100')

class FakeQuotes:
    def __init__(self):self.value=quote();self.error=False
    async def get(self):
        if self.error:raise DemoError('QUOTE_UNAVAILABLE')
        return deepcopy(self.value)
    async def close(self):pass

class RPC:
    """SQLite transaction simulator for HTTP contract. Does not execute PostgreSQL SQL."""
    def __init__(self,path):
        self.path=path;self.fail=False;self.commit_fail=False;self.lost_ack=False;self.paths=[]
        with sqlite3.connect(path) as c:
            c.execute('create table if not exists account(revision integer,payload text,sha256 text)')
            c.execute('create table if not exists events(seq integer primary key,id text unique,record text)')
    def __call__(self,request):
        self.paths.append(request.url.path);name=request.url.path.split('/')[-1];args=json.loads(request.content)
        assert name in ('aura_practice_load','aura_practice_commit','aura_practice_history')
        if self.fail or (self.commit_fail and name.endswith('_commit')):return httpx.Response(503,json={'error':'DUMMY_SAFE'})
        with sqlite3.connect(self.path) as c:
            c.row_factory=sqlite3.Row;c.execute('begin immediate')
            def account(duplicate=False):
                r=dict(c.execute('select * from account').fetchone());return dict(r,last_saved_at=NOW,duplicate=duplicate)
            if name.endswith('_load'):
                if not c.execute('select 1 from account').fetchone():c.execute('insert into account values(1,?,?)',(args['seed']['payload'],args['seed']['sha256']))
                result=account()
            elif name.endswith('_history'):
                rows=c.execute('select seq,record from events where (? is null or id=?) and (? is null or seq>?) order by seq desc limit ?',(args.get('event_id'),args.get('event_id'),args.get('after_seq'),args.get('after_seq'),args['row_limit'])).fetchall()
                result=[dict(json.loads(r['record']),seq=r['seq']) for r in rows]
            else:
                old=c.execute('select record from events where id=?',(args['operation_key'],)).fetchone()
                if old:
                    previous=unpack(json.loads(old['record']));incoming=args['new_events'][0]
                    result={'error':'IDEMPOTENCY_CONFLICT'} if previous.get('command_hash')!=incoming.get('command_hash') else account(True)
                elif account()['revision']!=args['expected_revision']:result={'error':'CONCURRENT_UPDATE'}
                else:
                    for e in args['new_events']:c.execute('insert into events(id,record) values(?,?)',(e['id'],json.dumps(e)))
                    c.execute('update account set revision=revision+1,payload=?,sha256=?',(args['new_state']['payload'],args['new_state']['sha256']));result=account()
        if self.lost_ack and name.endswith('_commit'):
            self.lost_ack=False;raise httpx.ReadTimeout('DUMMY_COMMITTED_BUT_ACK_LOST')
        return httpx.Response(200,json=result)

@pytest.fixture
def setup(tmp_path):
    rpc=RPC(tmp_path/'practice-test.sqlite3');q=FakeQuotes()
    def service():return Service(Store('https://abcdefghijkl.supabase.co','DUMMY_KEY_'+'x'*40,httpx.MockTransport(rpc)),q,lambda:NOW)
    return rpc,q,service

@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('exit_kind',['MANUAL','TP','SL'])
def test_full_cycle_actual_engine_rpc_persistence_independent_math(setup,side,exit_kind):
    rpc,q,factory=setup
    async def work():
        s=factory();body=command(side);opened=await s.command('OPEN',body);assert opened['confirmed']
        p=opened['view']['state']['position'];assert p['timeframe']=='QUOTE' and p['execution_context']=='MANUAL_FRESH_QUOTE'
        assert opened['view']['policy']['execution']=='MANUAL_FRESH_QUOTE'
        assert p['direction']==side and D(p['notional'])<=2000 and D(p['risk_usdt'])<=50
        assert D(opened['view']['available_balance'])>=0
        q.value=quote('101' if side=='LONG' else '99',2);await s.tick()
        s2=factory();assert (await s2.view())['state']['position']['id']==p['id']
        if exit_kind=='MANUAL':
            closed=await s2.command('CLOSE',dict(request_id=str(uuid.uuid4()),position_id=p['id']))
            receipt=closed['receipt']['payload']
        else:
            q.value=quote(('105' if side=='LONG' else '95') if exit_kind=='TP' else ('97' if side=='LONG' else '103'),3);await s2.tick()
            receipt=(await s2.view())['events'][0]['payload']
            assert receipt['exit_reason']==('TAKE_PROFIT_QUOTE' if exit_kind=='TP' else 'STOP_LOSS_QUOTE')
        state=(await s2.view())['state'];assert state['position'] is None
        with localcontext() as ctx:
            ctx.prec=64;size=D(p['size']);entry=D('100')*(D('1.0005') if side=='LONG' else D('.9995'))
            raw=D(q.value['price']);exit=raw*(D('.9995') if side=='LONG' else D('1.0005'))
            fee=lambda px:(px*size*D('.001')).quantize(D('.00000001'),rounding=ROUND_CEILING)
            gross=((exit-entry)*size*(1 if side=='LONG' else -1)).quantize(D('.00000001'),rounding=ROUND_HALF_EVEN)
            net=gross-fee(entry)-fee(exit)
            assert D(receipt['realized_pnl'])==net and D(state['balance'])==D('10000')+net
            assert D(state['fees'])==fee(entry)+fee(exit)
        assert [x['kind'] for x in reversed((await s2.view())['events'])]==['OPEN','UPDATE','CLOSE']
        assert all('/aura_practice_' in path for path in rpc.paths)
        await s.close();await s2.close()
    asyncio.run(work())


def test_idempotency_lost_ack_restart_and_changed_command(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();body=command();rpc.lost_ack=True
        with pytest.raises(DemoError):await s.command('OPEN',body)
        q.error=True;s2=factory();result=await s2.command('OPEN',body)
        assert result['duplicate'] and len(result['view']['events'])==1
        changed=dict(body,stop_loss='97')
        with pytest.raises(DemoError,match='IDEMPOTENCY_CONFLICT'):await s2.command('OPEN',changed)
        await s.close();await s2.close()
    asyncio.run(work())


def test_database_failure_does_not_report_open_and_recovers(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();await s.view();rpc.fail=True
        with pytest.raises(DemoError):await s.command('OPEN',command())
        rpc.fail=False;assert (await s.view())['state']['position'] is None
        assert (await s.command('OPEN',command()))['confirmed'];await s.close()
    asyncio.run(work())

@pytest.mark.parametrize('change,reason',[(dict(time_ms=NOW*1000-11000),'STALE_QUOTE'),(dict(time_ms=NOW*1000+3000),'STALE_QUOTE'),(dict(source='Other'),'INVALID_QUOTE'),(dict(price='NaN'),'INVALID_AMOUNT'),(dict(price='0'),'INVALID_AMOUNT')])
def test_bad_quotes_do_not_mutate_ledger(change,reason):
    old=seed(NOW);q=quote()|change
    with pytest.raises(DemoError,match=reason):transition(old,q,NOW,'OPEN',command())
    assert old['position'] is None and old['balance']=='10000'

@pytest.mark.parametrize('body',[dict(stop_loss='101'),dict(take_profit='99'),dict(stop_loss='NaN'),dict(expected_price='50')])
def test_invalid_stops_or_expected_price_rejected(body):
    with pytest.raises(DemoError):transition(seed(NOW),quote(),NOW,'OPEN',command()|body)


def test_concurrent_open_only_one_commit_and_no_state_overwrite(setup):
    rpc,q,factory=setup
    async def work():
        barrier=asyncio.Event();arrivals=0
        async def concurrent_rpc(request):
            nonlocal arrivals
            response=rpc(request)
            if request.url.path.endswith('aura_practice_load') and arrivals<2:
                arrivals+=1
                if arrivals==2:barrier.set()
                await barrier.wait()
            return response
        def instance():return Service(Store('https://abcdefghijkl.supabase.co','DUMMY_KEY_'+'x'*40,httpx.MockTransport(concurrent_rpc)),q,lambda:NOW)
        a=instance();b=instance()
        results=await asyncio.wait_for(asyncio.gather(a.command('OPEN',command()),b.command('OPEN',command('SHORT')),return_exceptions=True),5)
        assert sum(isinstance(x,dict) and x['confirmed'] for x in results)==1
        assert any(isinstance(x,DemoError) and x.code=='CONCURRENT_UPDATE' for x in results)
        assert len((await a.view())['events'])==1;await a.close();await b.close()
    asyncio.run(work())


def test_quote_regression_and_duplicate_update_and_stale_close(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();result=await s.command('OPEN',command());await s.tick();assert len((await s.view())['events'])==1
        q.value=quote('101',2);await s.tick();q.value=quote('100',1)
        with pytest.raises(DemoError,match='QUOTE_REGRESSION'):await s.tick()
        q.error=True
        with pytest.raises(DemoError):await s.command('CLOSE',dict(request_id=str(uuid.uuid4()),position_id=result['view']['state']['position']['id']))
        assert (await s.view())['state']['position'] is not None;await s.close()
    asyncio.run(work())


def test_api_authorization_csrf_schema_and_paper_only(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();app=FastAPI();app.include_router(router);app.state.practice=s
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_PRACTICE_OWNER'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://practice.invalid') as c:
                assert (await c.get('/api/practice/state')).status_code==401
                assert (await c.post('/api/practice/open',json=command())).status_code==401
                c.auth=('aura','DUMMY_PRACTICE_OWNER')
                assert (await c.post('/api/practice/open',json=command())).status_code==403
                assert (await c.post('/api/practice/open',json=command(),headers={'X-Aura-Paper':'local-only','Origin':'https://evil.invalid'})).status_code==403
                assert (await c.post('/api/practice/open',json=command()|{'size':'999'},headers={'X-Aura-Paper':'local-only'})).status_code==422
                r=await c.post('/api/practice/open',json=command(),headers={'X-Aura-Paper':'local-only'});assert r.status_code==200 and r.json()['confirmed']
                assert (await c.get('/api/practice/state')).json()['real_orders'] is False
        await s.close()
    asyncio.run(work())


def test_market_only_public_get_bounded_fresh_data():
    paths=[]
    def fake(r):
        paths.append((r.method,str(r.url)));return httpx.Response(200,json=[dict(id=1,time=NOW*1000,price='100')])
    async def work():
        q=Quotes(httpx.MockTransport(fake),clock=lambda:NOW);assert (await q.get())['source']==SOURCE;await q.close()
    asyncio.run(work());assert paths[0][0]=='GET' and paths[0][1].startswith('https://data-api.binance.vision/api/v3/trades?')


def test_disabled_practice_has_no_task_or_storage():
    from app.practice.service import configured
    with patch.dict('os.environ',AURA_PRACTICE_ENABLED='false'):
        s=configured();s.start();assert s.task is None and s.store is None


def test_sql_namespace_and_service_only_access():
    sql=Path('scripts/practice_schema.sql').read_text()
    assert 'public.aura_auto42_' not in sql and 'public.aura_forward_' not in sql
    assert 'for update' in sql and 'IDEMPOTENCY_CONFLICT' in sql and 'APPEND_ONLY' in sql
    assert 'to service_role' in sql and 'from public,anon,authenticated' in sql


def test_close_lost_ack_is_idempotent_after_restart(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();p=(await s.command('OPEN',command()))['view']['state']['position'];body=dict(request_id=str(uuid.uuid4()),position_id=p['id']);rpc.lost_ack=True
        with pytest.raises(DemoError):await s.command('CLOSE',body)
        fresh=factory();q.error=True;r=await fresh.command('CLOSE',body)
        assert r['duplicate'] and r['view']['state']['position'] is None
        assert [x['kind'] for x in r['view']['events']]==['CLOSE','OPEN']
        await s.close();await fresh.close()
    asyncio.run(work())


def test_extreme_short_gap_preserves_actual_loss_and_zero_available_cash(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();await s.command('OPEN',command('SHORT'));q.value=quote('1000',2);await s.tick()
        v=await s.view();assert v['state']['position'] is None and D(v['state']['balance'])<0 and D(v['available_balance'])==0
        with pytest.raises(DemoError):await s.command('OPEN',command('SHORT')|dict(expected_price='1000',stop_loss='1020',take_profit='950'))
        await s.close()
    asyncio.run(work())


def test_close_at_protective_level_uses_sl_cause_not_manual(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();p=(await s.command('OPEN',command()))['view']['state']['position'];q.value=quote('97',2)
        r=await s.command('CLOSE',dict(request_id=str(uuid.uuid4()),position_id=p['id']))
        assert r['receipt']['payload']['exit_reason']=='STOP_LOSS_QUOTE';await s.close()
    asyncio.run(work())


def test_cannot_close_different_position_or_open_second_position(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();await s.command('OPEN',command())
        with pytest.raises(DemoError,match='POSITION_CHANGED'):await s.command('CLOSE',dict(request_id=str(uuid.uuid4()),position_id='WRONG'))
        with pytest.raises(DemoError,match='POSITION_LIMIT'):await s.command('OPEN',command('SHORT'))
        assert len((await s.view())['events'])==1;await s.close()
    asyncio.run(work())


def test_monitor_clears_transient_error_after_database_recovers(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();s.error='PRACTICE_MONITOR_UNAVAILABLE_NO_CONFIRMATION';await s.tick();assert s.error is None
        await s.command('OPEN',command());s.error='TEMPORARY';await s.tick();assert s.error is None;await s.close()
    asyncio.run(work())


def test_stop_cannot_already_be_crossed_by_raw_quote_before_entry_slippage():
    with pytest.raises(DemoError,match='INVALID_STOPS_FOR_CURRENT_QUOTE'):
        transition(seed(NOW),quote(),NOW,'OPEN',command()|dict(stop_loss='100.03'))


def test_offline_browser_harness_refuses_render_and_missing_guard(tmp_path):
    from scripts.verify_practice_offline import run,child
    with patch.dict('os.environ',RENDER='true'):
        with pytest.raises(SystemExit,match='OFFLINE_ONLY'):run(tmp_path/'out.json')
        with pytest.raises(SystemExit,match='OFFLINE_GUARD'):child(tmp_path,9999)
    assert list(tmp_path.iterdir())==[]


def test_open_without_quote_never_creates_position(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();q.error=True
        with pytest.raises(DemoError,match='QUOTE_UNAVAILABLE'):await s.command('OPEN',command())
        v=await s.view();assert v['state']['position'] is None and v['events']==[];await s.close()
    asyncio.run(work())


def test_corrupt_database_response_is_503_not_definitive_client_error(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();app=FastAPI();app.include_router(router);app.state.practice=s
        async def corrupt():raise DemoError('CORRUPT_PORTFOLIO')
        with patch.object(s,'view',corrupt),patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_PRACTICE_OWNER'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://practice.invalid',auth=('aura','DUMMY_PRACTICE_OWNER')) as c:
                r=await c.get('/api/practice/state');assert r.status_code==503 and r.json()['confirmed'] is False
        await s.close()
    asyncio.run(work())


def test_failure_at_commit_returns_unconfirmed_and_does_not_apply_fee_or_position(setup):
    rpc,q,factory=setup
    async def work():
        s=factory();app=FastAPI();app.include_router(router);app.state.practice=s;body=command();rpc.commit_fail=True
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_PRACTICE_OWNER'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://practice.invalid',auth=('aura','DUMMY_PRACTICE_OWNER')) as c:
                r=await c.post('/api/practice/open',json=body,headers={'X-Aura-Paper':'local-only'})
                assert r.status_code==503 and r.json()['confirmed'] is False
                view=await s.view();assert view['state']['position'] is None and view['state']['balance']=='10000' and view['state']['fees']=='0' and view['events']==[]
                rpc.commit_fail=False;r=await c.post('/api/practice/open',json=body,headers={'X-Aura-Paper':'local-only'})
                assert r.status_code==200 and r.json()['confirmed'] is True
        await s.close()
    asyncio.run(work())
