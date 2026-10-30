"""Offline unit/integration fixtures are not evidence of market profitability."""
import asyncio
import copy
import gzip
import json
import math
from pathlib import Path
import time

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.hunter.engine import FAMILIES,Prepared,RULES,ema,net_rr
from app.hunter.market import PublicMarket,SOURCE,fresh_quote,parse_bars,validate_bars
from app.hunter.outcomes import cashflow,simulate
from app.hunter.store import Store,MODEL_HASH,LIVE_INPUT_CONTRACT,forward_outcome,validated
from app.hunter.main import Hunter,create_app
from research.hunter6.data import aggregate,load,audit
from research.hunter6.statistics import stats,bootstrap


def bars(n=320,step=300,start=0):
    # Explicit synthetic deterministic software fixture only.
    return [[start+i*step,100+math.sin(i/5),102+math.sin(i/5),98+math.sin(i/5),100+math.sin(i/5),100.] for i in range(n)]


def plan(side='LONG',at=96000):
    sign=1 if side=='LONG' else -1
    return {'id':'UNIT_ONLY','version':RULES['version'],'strategy':'TREND_PULLBACK','variant':'BASE','frame':'5m','direction':side,'signal_time':at,'valid_until':at+300,'entry':100.,'sl':100-sign*10,'tp':100+sign*20,'zone':[95,105],'atr':5.,'net_rr':1.8,'hold_bars':3,'technical_trigger':True,'reasons':['UNIT_TEST_NOT_MARKET'],'confirmation':'UNIT','cancel':'expiry','regime':'RANGE','source':SOURCE,'statistical_status':'UNVALIDATED','step':300,'model_sha256':MODEL_HASH}


def quote(now,price=100):return {'source':SOURCE,'bid':price-.01,'ask':price+.01,'last':price,'time':now,'received_at':now}


@pytest.mark.parametrize('change',[lambda b:b.__setitem__(0,True),lambda b:b.__setitem__(4,float('nan')),lambda b:b.__setitem__(5,-1),lambda b:b.__setitem__(2,90),lambda b:b.__setitem__(3,110)])
def test_hunter_history_invalid_types_and_ranges(change):
    b=bars(2);change(b[0])
    with pytest.raises(ValueError):validate_bars(b,300)


def test_hunter_history_gaps_duplicates_and_exact_aggregation():
    b=bars(9);expected=[b[0][0],b[0][1],max(x[2] for x in b[:3]),min(x[3] for x in b[:3]),b[2][4],300.]
    assert aggregate(b,900)[0]==expected
    with pytest.raises(ValueError):validate_bars([b[0],b[2]],300)
    with pytest.raises(ValueError):validate_bars([b[0],b[0]],300)
    assert len(aggregate([b[0],*b[2:]],900))==2
    raw=[[str(x[0]*1000),*map(str,x[1:])] for x in b]
    assert parse_bars(raw+[raw[0]],300)==b
    conflicting=copy.deepcopy(raw[0]);conflicting[4]='100.1'
    with pytest.raises(ValueError):parse_bars(raw+[conflicting],300)


def test_hunter_indicator_reference_and_no_future_mutation_or_fastpath_loss():
    assert np.allclose(ema(np.array([1.,2,3,4,5]),3)[2:],[2,3,4])
    original=bars(700);mutated=copy.deepcopy(original)
    for row in mutated[500:]:row[1:5]=[10000.,10002.,9998.,10000.]
    a,b=Prepared(original,'5m'),Prepared(mutated,'5m');prefix=Prepared(original[:500],'5m')
    for family in FAMILIES:
        fast=set(a.candidate_indices(family))
        for i in range(249,500):
            for variant in RULES['variants']:
                expected=a.plans(i,family,variant)
                assert expected==b.plans(i,family,variant)==prefix.plans(i,family,variant)
                if expected:assert i in fast
    with pytest.raises(ValueError):a.plans(300,'TREND_PULLBACK',cutoff=original[300][0])
    gap=original[:300]+[[r[0]+300,*r[1:]] for r in original[300:]]
    g=Prepared(gap,'5m');assert not g.valid[300:549].any();assert g.valid[549]


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_hunter_execution_independent_tp_sl_gap_and_cost_signs(side):
    p=plan(side);sign=1 if side=='LONG' else -1
    initial=[96000,100,102,98,100,1]
    target=[96300,105,125,100,120,1] if sign==1 else [96300,95,100,75,80,1]
    r=simulate(p,[initial,target],[],multiplier=1)
    assert r['entered'] and r['outcome']=='TP' and float(r['pnl_usdt'])>0
    both=[96300,100,125,75,100,1]
    r=simulate(p,[initial,both],[]);assert r['outcome']=='SL' and r['ambiguous'] and r['r']<0
    gap=[96300,80,85,75,80,1] if sign==1 else [96300,120,125,115,120,1]
    r=simulate(p,[initial,gap],[]);assert r['note']=='ADVERSE_STOP_GAP' and r['gross_reference_r']<-2
    assert r['r']==pytest.approx(float(r['pnl_usdt'])/float(r['risk_usdt']))


def test_hunter_entry_expiry_missing_data_timeout_unknown_and_funding_boundaries():
    p=plan();b=[[96000,110,115,105,110,1]]
    assert simulate(p,b,[])['outcome']=='NO_FILL'
    b=[[96000,100,102,98,100,1],[96600,100,102,98,100,1]]
    assert simulate(p,b,[])['note']=='OUTCOME_DATA_GAP'
    assert simulate(p,b[:1],[])['outcome']=='UNKNOWN'
    b=[[96000+i*300,100,102,98,100,1] for i in range(3)]
    r=simulate(p,b,[]);assert r['outcome']=='TIMEOUT' and r['r']<0
    p=plan(at=86400);b=[[86400,100,102,98,100,1],[86700,100,102,98,100,1]]
    debit=cashflow(p,100,110,86400,86700,b,[[86400,.0001]])
    credit=cashflow(p,100,110,86400,86700,b,[[86400,-.0001]])
    assert float(debit['funding_usdt'])==pytest.approx(.0102)
    assert float(credit['funding_usdt'])==0
    modeled=cashflow(p,100,110,86400,86700,b,[])
    assert modeled['missing_funding_settlements']==1 and 'MODELED' in modeled['funding_model']
    assert float(debit['pnl_usdt'])==pytest.approx(9.7798)


@pytest.mark.parametrize('patch',[{'time':1},{'ask':99},{'bid':float('nan')},{'source':'OTHER'},{'last':200},{'received_at':1}])
def test_hunter_quote_rejects_stale_conflicting_or_wrong_source(patch):
    q=quote(100);q.update(patch);assert not fresh_quote(q,100)


def test_hunter_public_transport_only_get_bounded_fixed_identity():
    seen=[]
    def respond(request):
        seen.append(request)
        assert request.method=='GET' and request.url.host=='api.bitget.com'
        assert request.url.params['symbol']=='BTCUSDT' and request.url.params['productType']=='USDT-FUTURES'
        return httpx.Response(200,json={'code':'00000','data':[]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            m=PublicMarket(client);await m.get('ticker')
            for path,params in [('place-order',{}),('ticker',{'symbol':'ETHUSDT'}),('ticker',{'url':'http://invalid'})]:
                with pytest.raises(ValueError):await m.get(path,**params)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(302,headers={'location':'http://invalid'}))) as c:
            with pytest.raises(ValueError):await PublicMarket(c).get('ticker')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*400001))) as c:
            with pytest.raises(ValueError):await PublicMarket(c).get('ticker')
    asyncio.run(run());assert len(seen)==1


def test_hunter_empty_registry_watch_durable_dedup_cancel_and_no_order_path(tmp_path,monkeypatch):
    now=96001.;path=tmp_path/'observer.sqlite';store=Store(path)
    p=plan();monkeypatch.setattr(Prepared,'plans',lambda self,i,family,**kw:[copy.deepcopy(p)] if family=='TREND_PULLBACK' else [])
    snap={'source':SOURCE,'frame':'5m','step':300,'bars':bars(320)[-260:],'quote':quote(now)}
    fund=[[86400,.0001],[115200,.0001]] # Future rate is intentionally invalid for CONFIRMED.
    store.observe(snap,fund,now,{'approved':[]});data=store.snapshot(now,{'5m':quote(now)})
    assert data['state']=='WATCH' and data['alerts']==[] and data['execution_enabled'] is False
    assert data['records'][0]['plan']['statistical_status']=='UNVALIDATED'
    assert data['records'][0]['input_sha256']==store.export_inputs('5m')['items'][0]['sha256']
    assert store.snapshot(now,{'5m':quote(now)},'OBSERVER_STOPPED')['records'][0]['state']=='NO TRADE'
    other=Store(path);other.observe(snap,fund,now+.1,{'approved':[]});assert len(other.snapshot(now+.1,{'5m':quote(now)})['records'])==1
    bad={**snap,'quote':quote(now+1,120)};other.observe(bad,fund,now+1,{'approved':[]})
    assert other.snapshot(now+1,{'5m':bad['quote']})['state']=='NO TRADE'
    assert other.snapshot(now+20,{'5m':snap['quote']})['state']=='NO TRADE'
    assert not validated(p,{'approved':[]})
    with pytest.raises(ValueError):Store('postgres://production/forbidden')


def test_hunter_confirmed_requires_exact_independent_registry_and_funding(tmp_path,monkeypatch):
    now=96001.;p=plan();monkeypatch.setattr(Prepared,'plans',lambda self,i,family,**kw:[copy.deepcopy(p)] if family=='TREND_PULLBACK' else [])
    proof={k:p[k] for k in ['strategy','frame','direction','variant']};proof.update(status='VALIDATED',independent=True,model_sha256=MODEL_HASH,evidence_sha256='a'*64,input_contract=LIVE_INPUT_CONTRACT)
    registry={'approved':[proof]};assert validated(p,registry)
    assert not validated(p,{'approved':[{**proof,'independent':False}]})
    assert not validated(p,{'approved':[{**proof,'model_sha256':'x'*64}]})
    assert not validated(p,{'approved':[{**proof,'evidence_sha256':1}]})
    assert not validated(p,{'approved':[{**proof,'input_contract':'ARCHIVE_EXPANDING_PREFIX'}]})
    assert not validated(p,{'approved':[{k:v for k,v in proof.items() if k!='input_contract'}]})
    snap={'source':SOURCE,'frame':'5m','step':300,'bars':bars(320)[-260:],'quote':quote(now)}
    store=Store(tmp_path/'valid.sqlite');store.observe(snap,[[57600,.0001],[86400,.0001]],now,registry)
    data=store.snapshot(now,{'5m':quote(now)});assert data['state']=='CONFIRMED' and len(data['alerts'])==1
    assert data['probability_tp_before_sl'] is None
    assert store.snapshot(now+6,{'5m':quote(now)})['alerts']==[]


def test_hunter_forward_never_certifies_pre_detection_candle_touches():
    p=plan();record={'plan':p,'quote':quote(96001),'detected_at':96001}
    fund=[[57600,.0001],[86400,.0001]]
    assert forward_outcome(record,[[96000,100,125,98,120,1]],fund)['outcome']=='UNKNOWN'
    r=forward_outcome(record,[[96000,100,102,98,100,1],[96300,100,125,85,100,1]],fund)
    assert r['outcome']=='SL' and r['r']<0
    assert forward_outcome(record,[[96300,100,102,98,100,1]],fund)['note']=='RECOVERY_CANDLE_GAP'


class OfflineMarket:
    async def close(self):pass
    async def snapshot(self,frame):raise ValueError('OFFLINE_FIXTURE')
    async def get(self,*a,**kw):return {'data':[]}


def test_hunter_app_owner_auth_readonly_scope_and_no_background_default(tmp_path):
    app=create_app(store=Store(tmp_path/'ui.sqlite'),market=OfflineMarket(),password='DUMMY_HUNTER_ONLY',observe=False)
    with TestClient(app) as client:
        assert client.get('/api/health').json()['observer_enabled'] is False
        assert client.get('/').status_code==401
        auth=('owner','DUMMY_HUNTER_ONLY')
        assert client.get('/',auth=auth).status_code==200
        assert client.get('/static/hunter6/hunter.js',auth=auth).status_code==200
        assert client.get('/static/hunter6/eligibility.json',auth=auth).status_code==404
        assert client.post('/api/hunter/snapshot',auth=auth).status_code==405
        data=client.get('/api/hunter/snapshot',auth=auth).json();assert data['state']=='NO TRADE' and data['alerts']==[]
        assert 'DUMMY_HUNTER_ONLY' not in json.dumps(data)
    app=create_app(store=Store(tmp_path/'unset.sqlite'),market=OfflineMarket(),password='',observe=False)
    with TestClient(app) as client:assert client.get('/').status_code==503


def test_hunter_observer_recovers_without_swallowing_cancellation(tmp_path):
    async def run():
        h=Hunter(Store(tmp_path/'reconnect.sqlite'),OfflineMarket(),{'approved':[]})
        await h.cycle();assert h.error=='MARKET_DATA_UNAVAILABLE' and h.failures==1
        task=asyncio.create_task(h.run());await asyncio.sleep(.01);task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(run())


def test_hunter_stats_unknowns_not_wins_and_small_block_intervals():
    ts=[{'id':'a','signal_time':0,'entered':True,'outcome':'TP','exit_time':300,'pnl_usdt':'20','r':2}, {'id':'b','signal_time':600,'entered':True,'outcome':'SL','exit_time':900,'pnl_usdt':'-10','r':-1}, {'id':'c','signal_time':1200,'entered':True,'outcome':'UNKNOWN','pnl_usdt':None,'r':None}]
    m=stats(ts);assert m['closed']==2 and m['win_rate']==.5 and m['profit_factor']==2 and m['expectancy_R']==.5 and m['max_drawdown_usdt']==10
    assert bootstrap(ts[:2],'test',0,2000)['status']=='INSUFFICIENT_EVIDENCE'


def test_hunter_saved_real_history_integrity_and_funding_limit():
    rows,funding,manifest=load();data=audit(rows,funding,manifest)
    assert data['base_candles']==551520 and data['missing_candles']==0
    assert data['frame_candles']=={'5m':551520,'15m':183840,'1h':45960,'4h':11490}
    assert data['funding_coverage_complete'] is False and funding[0][0]==1785542400


@pytest.mark.parametrize('registry',[None,[],{'approved':None},{'approved':'bad'},{'approved':[None,1,{}]}])
def test_hunter_corrupt_registry_fails_closed(registry):
    assert not validated(plan(),registry)


def test_hunter_worker_success_after_disconnect_and_persistent_watermark(tmp_path,monkeypatch):
    now=96001.;p=plan();monkeypatch.setattr(Prepared,'plans',lambda self,i,family,**kw:[copy.deepcopy(p)] if family=='TREND_PULLBACK' else [])
    monkeypatch.setattr('app.hunter.main.time.time',lambda:now)
    class Recovering(OfflineMarket):
        down=True
        async def snapshot(self,frame):
            if self.down or frame!='5m':raise ValueError('FIXTURE_DISCONNECT')
            return {'source':SOURCE,'frame':'5m','step':300,'bars':bars(320)[-260:],'quote':quote(now)}
    async def run():
        m=Recovering();s=Store(tmp_path/'recover.sqlite');h=Hunter(s,m,{'approved':[]})
        await h.cycle();assert h.error and not h.quotes
        m.down=False;await h.cycle();assert h.error is None and h.failures==0
        d=s.snapshot(now,h.quotes,h.error);assert d['fresh_frames']==['5m'] and d['state']=='WATCH'
        h=Hunter(Store(s.path),m,{'approved':[]});await h.cycle()
        assert len(h.store.snapshot(now,h.quotes)['records'])==1
    asyncio.run(run())


def test_hunter_snapshot_closed_bar_identity_and_stale_rejection(monkeypatch):
    now=96001.;monkeypatch.setattr('app.hunter.market.time.time',lambda:now)
    rows=bars(261,start=18000)
    raw=[[str(b[0]*1000),*map(str,b[1:])] for b in rows]
    wrong=[False]
    def response(req):
        value=raw if req.url.path.endswith('/candles') else [{'symbol':'ETHUSDT' if wrong[0] else 'BTCUSDT','bidPr':'99.99','askPr':'100.01','lastPr':'100','ts':str(int(now*1000))}]
        return httpx.Response(200,json={'code':'00000','data':value})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as c:
            m=PublicMarket(c);snap=await m.snapshot('5m')
            assert len(snap['bars'])==260 and snap['bars'][-1][0]==95700
            assert all(b[0]+300<=now for b in snap['bars'])
            wrong[0]=True
            with pytest.raises(ValueError,match='IDENTITY'):await m.snapshot('5m')
    asyncio.run(run())
