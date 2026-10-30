"""Offline forward-evidence and observer recovery regressions; no edge claims."""
import asyncio
import copy
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.hunter.main import Hunter, create_app
from app.hunter.market import PublicMarket, SOURCE, LIVE_INPUT_CONTRACT
from app.hunter.store import Store, evidence_hash, validated, MODEL_HASH
from research.hunter6.forward import audit_page
from scripts.hunter6_capture import capture
from tests.test_hunter6 import OfflineMarket, bars, quote, plan


def sample(now=96001.):
    return {'source':SOURCE,'frame':'5m','step':300,'bars':bars(320)[-260:],'quote':quote(now)}


def test_evidence_records_empty_decisions_and_replays_exact_seed_after_restart(tmp_path):
    path=tmp_path/'capture.sqlite';s=Store(path);snap=sample()
    s.observe(snap,[],96001.,{'approved':[]})
    first=s.export_inputs('5m')
    assert len(first['items'])==1 and first['items'][0]['payload']['snapshot']==snap
    assert audit_page(first)['inputs_verified']==1
    assert audit_page(first)['approved_for_confirmed']==[]
    assert audit_page(first)['profitability_evaluated'] is False
    assert first['items'][0]['payload']['input_contract']==LIVE_INPUT_CONTRACT
    s=Store(path);s.observe(snap,[],96002.,{'approved':[]})
    assert s.export_inputs('5m')==first
    assert s.export_inputs('5m',after=first['next_after'])['items']==[]


@pytest.mark.parametrize('length',[250,259,261,320])
def test_observer_refuses_variable_seed_window_before_writing(tmp_path,length):
    s=Store(tmp_path/'bad.sqlite');snap=sample();snap['bars']=bars(320)[-length:]
    with pytest.raises(ValueError,match='WINDOW'):s.observe(snap,[],96001.,{'approved':[]})
    assert s.export_inputs('5m')['items']==[]
    with s.connection() as db:assert db.execute('SELECT COUNT(*) FROM watermarks').fetchone()[0]==0


def test_evidence_rejects_tamper_model_mismatch_and_manufactured_plan(tmp_path):
    s=Store(tmp_path/'audit.sqlite');s.observe(sample(),[],96001.,{'approved':[]})
    original=s.export_inputs('5m')
    p=copy.deepcopy(original);p['items'][0]['payload']['snapshot']['bars'][0][5]+=1
    with pytest.raises(ValueError,match='HASH'):audit_page(p)
    p['items'][0]['sha256']=evidence_hash(p['items'][0]['payload'])
    p['items'][0]['payload']['plans']=[{'fake':'invented profitable scenario'}]
    p['items'][0]['sha256']=evidence_hash(p['items'][0]['payload'])
    with pytest.raises(ValueError,match='REPRODUCTION'):audit_page(p)
    p=copy.deepcopy(original);p['items'][0]['payload']['model_sha256']='0'*64
    p['items'][0]['sha256']=evidence_hash(p['items'][0]['payload'])
    with pytest.raises(ValueError,match='MODEL'):audit_page(p)


def test_evidence_pagination_and_internal_missing_cutoff_are_explicit(tmp_path):
    s=Store(tmp_path/'pages.sqlite');s.observe(sample(),[],96001.,{'approved':[]})
    later=sample(96601.);later['bars']=[[r[0]+600,*r[1:]] for r in later['bars']]
    s.observe(later,[],96601.,{'approved':[]})
    page=s.export_inputs('5m',limit=1);assert page['has_more']
    tail=s.export_inputs('5m',after=page['next_after'],limit=1)
    assert len(tail['items'])==1 and not tail['has_more']
    full=s.export_inputs('5m');report=audit_page(full)
    assert report['internal_gaps']==[{'after':96000,'before':96600,'missing_cutoffs':1}]
    assert report['complete_history_claimed'] is False


def test_old_contract_cannot_authorize_fixed_window_signals():
    p=plan();proof={k:p[k] for k in ('strategy','frame','direction','variant')}
    proof.update(status='VALIDATED',independent=True,model_sha256=MODEL_HASH,evidence_sha256='a'*64,
                 input_contract='BITGET_NATIVE_260_CLOSED_BARS_V1')
    assert not validated(p,{'approved':[proof]})


@pytest.mark.parametrize('closed_count,include_forming,accepted',[(259,True,False),(260,True,True),(261,False,True)])
def test_market_reserves_forming_row_but_requires_260_closed(monkeypatch,closed_count,include_forming,accepted):
    now=96001.;monkeypatch.setattr('app.hunter.market.time.time',lambda:now)
    rows=bars(closed_count,start=96000-closed_count*300)
    if include_forming:rows.append([96000,100,102,98,100,1])
    def respond(req):
        if req.url.path.endswith('/candles'):
            assert req.url.params['limit']=='261'
            data=[[str(r[0]*1000),*map(str,r[1:])] for r in rows]
        else:data=[{'symbol':'BTCUSDT','bidPr':'99.99','askPr':'100.01','lastPr':'100','ts':'96001000'}]
        return httpx.Response(200,json={'code':'00000','data':data})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            if not accepted:
                with pytest.raises(ValueError,match='INCOMPLETE'):await PublicMarket(client).snapshot('5m')
            else:
                snap=await PublicMarket(client).snapshot('5m')
                assert len(snap['bars'])==260 and snap['bars'][-1][0]==95700
    asyncio.run(run())


def test_owner_export_is_readonly_bounded_and_disabled_observer_is_explicit(tmp_path):
    s=Store(tmp_path/'api.sqlite');s.observe(sample(),[],96001.,{'approved':[]})
    app=create_app(store=s,market=OfflineMarket(),password='DUMMY_ONLY',observe=False)
    with TestClient(app) as c:
        auth=('owner','DUMMY_ONLY');url='/api/hunter/inputs?frame=5m'
        assert c.get(url).status_code==401
        assert len(c.get(url,auth=auth).json()['items'])==1
        for suffix in ['&limit=101','&after=-1','&limit=0']:
            assert c.get(url+suffix,auth=auth).status_code==422
        assert c.get('/api/hunter/inputs?frame=../private',auth=auth).status_code==422
        assert c.post(url,auth=auth).status_code==405
        state=c.get('/api/hunter/snapshot',auth=auth).json()
        assert state['reason']=='OBSERVER_DISABLED' and not state['observer']['running']


def test_storage_failure_cannot_silently_kill_observer_retry_loop(tmp_path,monkeypatch):
    async def run():
        h=Hunter(Store(tmp_path/'retry.sqlite'),OfflineMarket(),{'approved':[]})
        calls=[];sleeps=[]
        async def cycle():
            calls.append(1)
            if len(calls)==1:raise OSError('DUMMY_SENSITIVE_INTERNAL_DETAIL')
            h.error=None;h.failures=0;h.cycles+=1
        async def sleep(delay):
            sleeps.append(delay)
            if len(sleeps)==1:
                assert h.error=='OBSERVER_CYCLE_FAILED' and not h.quotes
                return
            raise asyncio.CancelledError
        monkeypatch.setattr(h,'cycle',cycle);monkeypatch.setattr('app.hunter.main.asyncio.sleep',sleep)
        with pytest.raises(asyncio.CancelledError):await h.run()
        assert len(calls)==2 and h.error is None and sleeps==[10,5]
    asyncio.run(run())


def test_partial_frame_failure_is_visible_without_disabling_good_frame(tmp_path,monkeypatch):
    monkeypatch.setattr('app.hunter.main.time.time',lambda:96001.)
    class Partial(OfflineMarket):
        async def snapshot(self,frame):
            if frame=='5m':return sample()
            raise ValueError('DUMMY_PRIVATE_EXCEPTION_DETAIL')
    async def run():
        h=Hunter(Store(tmp_path/'partial.sqlite'),Partial(),{'approved':[]})
        await h.cycle()
        assert h.error is None and list(h.quotes)==['5m']
        assert h.frame_errors=={f:'PUBLIC_FRAME_UNAVAILABLE' for f in ['15m','1h','4h']}
    asyncio.run(run())


def test_evidence_failure_rolls_back_watermark_so_recovery_can_capture(tmp_path):
    s=Store(tmp_path/'atomic.sqlite')
    with pytest.raises(ValueError):s.observe(sample(),[[86400,float('nan')]],96001.,{'approved':[]})
    with s.connection() as db:assert db.execute('SELECT COUNT(*) FROM watermarks').fetchone()[0]==0
    assert s.export_inputs('5m')['items']==[]
    s.observe(sample(),[],96001.,{'approved':[]})
    assert audit_page(s.export_inputs('5m'))['inputs_verified']==1


def test_stopped_task_is_degraded_and_never_reported_as_running(tmp_path):
    class Stopped:
        def done(self):return True
    app=create_app(store=Store(tmp_path/'stopped.sqlite'),market=OfflineMarket(),password='DUMMY_ONLY',observe=False)
    with TestClient(app) as c:
        app.state.observer_task=Stopped()
        assert c.get('/api/health').status_code==503
        d=c.get('/api/hunter/snapshot',auth=('owner','DUMMY_ONLY')).json()
        assert not d['observer']['running'] and d['reason']=='OBSERVER_STOPPED'
        assert d['state']=='NO TRADE' and d['alerts']==[]


def test_saved_public_native_windows_reproduce_without_network(monkeypatch):
    import research.hunter6.forward as reproduction
    from research.aura5_cost_audit.baseline import engine,MODEL_HASH as original_hash
    monkeypatch.setattr(reproduction,'Prepared',engine.Prepared)
    monkeypatch.setattr(reproduction,'MODEL_HASH',original_hash)
    folder=Path(__file__).resolve().parents[1]/'docs/aura6/native_probe'
    for frame in ['5m','15m','1h','4h']:
        report=audit_page(json.loads((folder/(frame+'.json')).read_text()))
        assert report['inputs_verified']==1 and report['approved_for_confirmed']==[]
        assert not report['profitability_evaluated']


def test_bounded_capture_reports_unavailable_frames_instead_of_inventing_inputs(tmp_path):
    result=asyncio.run(capture(tmp_path/'capture',OfflineMarket()))
    assert result['error']=='MARKET_DATA_UNAVAILABLE'
    assert len(result['frame_errors'])==4 and result['orders']==0
    assert all(r['inputs_verified']==0 for r in result['audits'])
    assert result['states']['state']=='NO TRADE'


def test_cycle_uses_fresh_same_market_quote_after_parallel_frame_wait(tmp_path,monkeypatch):
    """Early frame quote can expire while gather waits for slower candle fetches."""
    import app.hunter.main as module
    from app.hunter.market import STEPS, fresh_quote
    now=7200000.
    monkeypatch.setattr(module.time,'time',lambda:now)
    class DelayedCohort(OfflineMarket):
        async def snapshot(self,frame):
            step=STEPS[frame]
            return {'source':SOURCE,'frame':frame,'step':step,
                    'bars':bars(260,step,int(now)-260*step),
                    'quote':quote(now-10 if frame=='5m' else now)}
    async def run():
        s=Store(tmp_path/'cohort.sqlite');h=Hunter(s,DelayedCohort(),{'approved':[]})
        await h.cycle()
        assert h.frame_errors=={}
        for frame in STEPS:
            page=s.export_inputs(frame)
            assert len(page['items'])==1
            q=page['items'][0]['payload']['snapshot']['quote']
            assert q==quote(now) and fresh_quote(q,now)
            assert audit_page(page)['inputs_verified']==1
    asyncio.run(run())


@pytest.mark.parametrize('bad',['stale','future','foreign_quote','foreign_snapshot'])
def test_cycle_never_refreshes_from_unverified_quote_cohort(tmp_path,monkeypatch,bad):
    import app.hunter.main as module
    from app.hunter.market import STEPS
    now=7200000.
    monkeypatch.setattr(module.time,'time',lambda:now)
    class BadCohort(OfflineMarket):
        async def snapshot(self,frame):
            step=STEPS[frame];q=quote(now-10)
            source=SOURCE
            if frame=='4h':
                if bad=='future':q=quote(now+1)
                if bad=='foreign_quote':q=quote(now);q['source']='OTHER'
                if bad=='foreign_snapshot':q=quote(now);source='OTHER'
            return {'source':source,'frame':frame,'step':step,
                    'bars':bars(260,step,int(now)-260*step),'quote':q}
    async def run():
        s=Store(tmp_path/'bad-cohort.sqlite');h=Hunter(s,BadCohort(),{'approved':[]})
        await h.cycle()
        assert h.quotes=={} and len(h.frame_errors)==4
        assert all(s.export_inputs(frame)['items']==[] for frame in STEPS)
    asyncio.run(run())
