"""Isolated synthetic technical fixtures. Not market profitability evidence."""
import asyncio,json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
from unittest.mock import patch
import httpx,pytest
from fastapi import FastAPI
from app.active43 import core
from app.active43.core import initial,advance,plan,validate,SCOPE
from app.active43.strategies import PARAMETERS,STEPS,signals,config
from app.active43.service import Service,configured
from app.active43.api import router
from app.automated.engine import DemoError,risk_reason
from app.lab.models import digest,Bar
from scripts.verify_active43 import FixtureMarket
from scripts.verify_auto42_execution import check_accounting

class MemoryStore:
    backend='TEST_ONLY_MEMORY';durable=False
    def __init__(self,cfg,now):self.state=initial(now,cfg);self.revision=1;self.events=[];self.fail=False;self.lock=asyncio.Lock()
    async def close(self):pass
    async def load(self,now):
        if self.fail:raise DemoError('STORAGE_UNAVAILABLE_OUTCOME_UNKNOWN')
        return dict(state=deepcopy(self.state),revision=self.revision,last_saved_at=now)
    async def lookup(self,key):return next((deepcopy(e) for e in self.events if e['id']==key),None)
    async def history(self,epoch=None,after=None,limit=50,key=None,kind=None,before=None):
        rows=[dict(deepcopy(e),seq=i+1) for i,e in enumerate(self.events) if (epoch is None or e['epoch']==epoch) and (key is None or e['id']==key) and (kind is None or e['kind']==kind)]
        if after is not None:rows=[e for e in rows if e['seq']>after]
        else:rows.reverse()
        if before is not None:rows=[e for e in rows if e['seq']<before]
        return rows[:limit]
    async def commit(self,revision,state,events,key):
        async with self.lock:
            if self.fail:raise DemoError('STORAGE_UNAVAILABLE_OUTCOME_UNKNOWN')
            if await self.lookup(key):return dict(await self.load(1),duplicate=True)
            if revision!=self.revision:raise DemoError('CONCURRENT_UPDATE')
            validate(state);self.state=deepcopy(state);self.revision+=1;self.events.extend(deepcopy(events))
            return dict(await self.load(1),duplicate=False)


def setup(side='LONG',tf='15m',name='DONCHIAN'):
    market=FixtureMarket(side,tf);now=[market.bars[-1].time+market.step+30];cfg=config(name,tf)
    store=MemoryStore(cfg,now[0]);svc=Service(store,market,cfg,clock=lambda:now[0]);return market,now,store,svc


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('tf',list(STEPS))
@pytest.mark.parametrize('exit_kind',['SL','TP','BOTH'])
def test_signal_open_update_restart_close_costs_and_duplicates(side,tf,exit_kind):
    async def run():
        market,now,store,svc=setup(side,tf)
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        market.add();now[0]+=market.step;await svc.tick()
        assert store.state['pending'] and store.state['position'] is None
        market.add();now[0]+=market.step
        other=Service(store,market,svc.config,clock=lambda:now[0])
        await asyncio.gather(svc.tick(),other.tick());p=deepcopy(store.state['position']);assert p
        await svc.close();svc=Service(store,market,svc.config,clock=lambda:now[0])
        assert (await svc.load())['state']['position']==p
        await svc.tick();market.signal=False;market.add();now[0]+=market.step;await svc.tick()
        assert store.state['position'] and any(e['kind']=='POSITION_UPDATE' for e in store.events)
        long=side=='LONG';tp=exit_kind=='TP'
        high='105' if exit_kind=='BOTH' or long==tp else '101';low='95' if exit_kind=='BOTH' or long!=tp else '99'
        market.add(high=high,low=low);now[0]+=market.step;await svc.tick();await svc.tick()
        closed=[e['payload'] for e in store.events if e['kind']=='CLOSE'];opened=[e for e in store.events if e['kind']=='OPEN']
        assert len(opened)==len(closed)==1
        assert closed[0]['exit_reason']==('STOP_LOSS_AMBIGUOUS' if exit_kind=='BOTH' else 'TAKE_PROFIT' if tp else 'STOP_LOSS')
        assert closed[0]['exit_time']==market.bars[-1].time+market.step
        check_accounting(p,closed[0],store.state)
        assert not (await svc.dashboard())['production_paper_verified']
        await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize('name',list(PARAMETERS))
def test_all_hypotheses_prefix_causal_no_future_candles(name):
    bars=[]
    for i in range(450):
        price=D(100)+D(i%30)/10+D(i)/100
        bars.append(Bar(i*900,price,price+1,price-1,price+D('.1'),D(100+i%11)))
    full=signals(bars,name)
    for end in (250,301,449):assert signals(bars[:end],name)==full[:end]
    changed=bars+[replace(bars[-1],time=450*900,open=D(300),high=D(400),low=D(200),close=D(350))]
    assert signals(changed,name)[:-1]==full


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_trailing_stop_only_effective_on_later_bar(side):
    market,now,_,_=setup(side,name='TREND_ATR');s=initial(now[0],config('TREND_ATR'));s.update(mode='ON',watermark=market.bars[-1].time+900,last_bar_hash=digest(market.bars[-1].data()))
    at=s['watermark'];decision=dict(direction=side,reason='TEST_ONLY',source=core.SOURCE,signal_at=at+900,
        stop_loss='98' if side=='LONG' else '102',take_profit='110' if side=='LONG' else '90',atr='1')
    s['pending']=dict(decision,signal_at=at)
    market.add(high='103' if side=='LONG' else '101',low='99' if side=='LONG' else '97',close='102' if side=='LONG' else '98')
    decision['direction']=None
    s,events=advance(s,market.bars,decision,at+930)
    assert s['position'] and not any(e['kind']=='CLOSE' for e in events)
    assert any(e['kind']=='STOP_UPDATE' for e in events)
    active=D(s['position']['active_stop']);assert active%D(core.FILTERS['price_tick'])==0
    assert active>D(s['position']['entry_price']) if side=='LONG' else active<D(s['position']['entry_price'])
    assert D(s['position']['stop_loss'])==D('98' if side=='LONG' else '102')
    validate(s)


def test_no_signal_stale_database_failure_recovery_and_stops():
    async def run():
        market,now,store,svc=setup();market.signal=False
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        market.add();now[0]+=900;await svc.tick();assert store.state['position'] is None
        market.failure='MARKET_UNAVAILABLE';now[0]+=300;await svc.tick();assert store.state['mode']=='PAUSED' and store.state['data_recovery_armed']
        market.failure=None;now[0]+=300;await svc.tick();assert store.state['mode']=='ON'
        market.signal=True;market.add();now[0]+=900;await svc.tick();assert store.state['pending']
        before=deepcopy(store.state);store.fail=True;market.add();now[0]+=900
        with pytest.raises(DemoError):await svc.tick()
        assert store.state==before
        store.fail=False;await svc.tick();assert store.state['position']
        before=deepcopy(store.state)
        for _ in range(40):market.add()
        now[0]+=40*900;await svc.tick();assert store.state['watermark']>before['watermark'] and store.state['pending'] is None
        await svc.control('STOP','b'*32);assert store.state['mode']=='OFF' and store.state['position']
        market.add(high='105');now[0]+=900;await svc.tick();assert store.state['position'] is None
        assert len([e for e in store.events if e['kind']=='OPEN'])==1
        await svc.close()
    asyncio.run(run())


def test_risk_and_lot_filters_are_independent_of_signal():
    market,now,store,svc=setup();s=store.state;s['mode']='ON'
    p=dict(direction='LONG',signal_at=now[0]//900*900,stop_loss='98',take_profit='104',reason='TEST_ONLY',source=core.SOURCE)
    for field,value,reason in [('day_low_equity','9800','DAILY_LOSS_LIMIT'),('max_drawdown_pct','10','DRAWDOWN_LIMIT')]:
        bad=deepcopy(s);bad[field]=value
        with pytest.raises(DemoError,match=reason):core.open_position(bad,p,market.bars[-1],now[0])
    core.open_position(s,p,market.bars[-1],now[0]);pos=s['position']
    assert D(pos['size'])%D(core.FILTERS['qty_step'])==0
    assert D(pos['risk_usdt'])<=D(50) and D(pos['notional'])<=2000 and D(s['balance'])>=0
    with pytest.raises(DemoError,match='POSITION_LIMIT'):core.open_position(s,p,market.bars[-1],now[0])


def test_owner_csrf_independent_token_and_no_signal_order_routes(monkeypatch):
    async def run():
        market,now,store,svc=setup();app=FastAPI();app.include_router(router);app.state.active43=svc
        monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','dummy-active43-owner')
        monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET','dummy-active43-scheduler-token-000000000000')
        monkeypatch.setenv('AURA_AUTO42_SCHEDULER_SECRET','dummy-separate-auto42-scheduler-0000000000')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            for path in ('status','quote','journal','trades'):assert (await client.get('/api/active43/'+path)).status_code==401
            assert (await client.post('/api/active43/tick',headers={'X-Aura-Auto42-Token':'dummy-separate-auto42-scheduler-0000000000'})).status_code==401
            auth=('aura','dummy-active43-owner')
            assert (await client.get('/api/active43/status',auth=auth)).status_code==200
            body=dict(action='START',request_id='a'*32,expected_revision=1,confirmation='START EXPERIMENTAL PAPER')
            assert (await client.post('/api/active43/control',auth=auth,json=body)).status_code==403
            assert (await client.post('/api/active43/control',auth=auth,json=body,headers={'X-Aura-Paper':'local-only','Origin':'https://evil.invalid'})).status_code==403
            assert (await client.post('/api/active43/control',auth=auth,json=body,headers={'X-Aura-Paper':'local-only'})).status_code==200
            for path in ('open','close','signal','backtest'):assert (await client.post('/api/active43/'+path,auth=auth,json={})).status_code==404
            assert (await client.get('/api/active43/trades?limit=201',auth=auth)).status_code==422
            assert store.state['mode']=='ON' and store.state['position'] is None
        await svc.close()
    asyncio.run(run())


def test_default_off_has_no_account_or_network(monkeypatch):
    monkeypatch.delenv('AURA_ACTIVE43_ENABLED',raising=False)
    service=configured();assert service.store is None and service.market is None
    assert service.reason=='ACTIVE43_DISABLED'


def test_config_scope_and_policy_tampering_fail_closed():
    s=initial(1700000000)
    for key,value in [('scope','AURA42'),('active_policy_hash','changed'),('config_hash','wrong')]:
        bad=deepcopy(s);bad[key]=value
        with pytest.raises(DemoError):validate(bad)

@pytest.mark.parametrize('name',list(PARAMETERS))
def test_all_strategy_plans_persist_as_canonical_json(name):
    from app.lab.models import canonical
    from app.lab.strategies import Decision
    b=Bar(1700000100,D(100),D(101),D(99),D(100),D(100))
    value=plan(Decision('LONG',D(2),D(4),reason='TEST_ONLY'),b,900,D(2) if name=='TREND_ATR' else None)
    assert json.loads(canonical(value))==value

def test_disabled_feature_does_not_load_broken_selection(monkeypatch):
    import app.active43.service as service
    monkeypatch.delenv('AURA_ACTIVE43_ENABLED',raising=False)
    def forbidden():raise DemoError('CONFIG_INVALID')
    monkeypatch.setattr(service,'selected',forbidden)
    assert service.configured().store is None

def test_experiment_selection_uses_no_final_test_fields():
    from scripts.research_active43 import score
    from copy import deepcopy
    row=dict(development=dict(metrics=dict(trades=30,net_profit='10',profit_factor='1.1',max_drawdown_pct='1')),validation=dict(metrics=dict(trades=15,net_profit='5',profit_factor='1.1',max_drawdown_pct='1')))
    before=score(row);row['final_test']={'metrics':{'net_profit':'100000000'}}
    assert score(row)==before
    row['validation']['metrics']['net_profit']='-1'
    assert not score(row)[0]

def test_daily_limit_owner_restart_only_after_new_utc_day_keeps_balance():
    async def run():
        market,now,store,svc=setup();store.state.update(mode='PAUSED',balance='9790',equity='9790',realized_pnl='-210',day_low_equity='9790')
        with patch('app.active43.service.scheduler_configured',return_value=True):
            with pytest.raises(DemoError,match='DAILY_LOSS_LIMIT'):await svc.control('START','a'*32,1)
            market.bars=[replace(b,time=b.time+86400) for b in market.bars];now[0]+=86400
            await svc.control('START','b'*32,1)
        assert store.state['mode']=='ON' and store.state['balance']=='9790' and store.state['realized_pnl']=='-210'
        assert store.state['day_start_equity']=='9790' and core.POLICY['daily_loss_pct']=='2'
        await svc.close()
    asyncio.run(run())

def test_current_quote_pnl_reads_same_position_without_writing():
    async def run():
        from app.active43.core import SOURCE as QUOTE_SOURCE,IDENTITY
        market,now,store,svc=setup()
        class Quote:
            async def get(self):return dict(price='101',time_ms=now[0]*1000,trade_id=1,source=QUOTE_SOURCE,identity=IDENTITY)
            async def close(self):pass
        svc.quotes=Quote()
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        market.add();now[0]+=900;await svc.tick();market.add();now[0]+=900;await svc.tick()
        before=deepcopy(store.state);count=len(store.events);app=FastAPI();app.include_router(router);app.state.active43=svc
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='dummy-active43-owner'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',auth=('aura','dummy-active43-owner')) as client:
                r=await client.get('/api/active43/quote');assert r.status_code==200
                b=r.json();assert b['read_only'] and b['position_id']==store.state['position']['id']
                expected=core.paper.liquidation_equity(store.state,D(101))-D(store.state['balance'])-D(store.state['position']['entry_fee'])
                assert D(b['position_net_pnl_at_quote'])==expected
        assert store.state==before and len(store.events)==count
        await svc.close()
    asyncio.run(run())

def test_passive_evidence_failure_cannot_block_protective_close():
    async def run():
        market,now,store,svc=setup()
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        market.add();now[0]+=900;await svc.tick();market.add();now[0]+=900;await svc.tick();assert store.state['position']
        market.signal=False;market.add(low='97');now[0]+=900
        with patch('app.active43.service.observe',side_effect=RuntimeError('TEST_ONLY_MONITOR_FAILURE')):await svc.tick()
        assert store.state['position'] is None and store.state['trades']==1
        assert store.state['monitor_error']=='EVIDENCE_CAPTURE_FAILED'
        assert not (await svc.dashboard())['production_paper_verified']
        assert len([e for e in store.events if e['kind']=='CLOSE'])==1
        await svc.close()
    asyncio.run(run())

def test_bare_or_corrupt_live_proof_flag_is_not_production_verification():
    from app.active43.evidence import verified
    s=initial(1700000000)
    for value in ('corrupt',True,{'scope':SCOPE,'natural_render_cycle':True}, {'scope':SCOPE,'natural_render_cycle':True,'open':{'origin':True}}):
        s['production_cycle']=value
        assert not verified(s)
