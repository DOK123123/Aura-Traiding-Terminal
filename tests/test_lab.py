"""Offline independent research validity/execution/isolation regressions."""
import ast
import asyncio
from dataclasses import replace
from decimal import Decimal as D,localcontext
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest

from app.lab.models import Bar,Baseline,LabError,STEPS,WARMUP_4H,validate_series,digest,SOURCE
from app.lab.data import Loader,aggregate
from app.lab.strategies import Decision,decisions,PARAMETERS
from app.lab.execution import simulate,metrics
from app.lab.experiment import execute,software_hash
from app.lab.storage import Store,unpack
from app.lab.service import Service
from tests.legacy_terminal import app
from tests.test_audit_math import nearest_ticks,ceiling_ticks,TICKS

END=1800000000//14400*14400


def bar(stamp,price='100',high=None,low=None,op=None):
    p=D(price);return Bar(stamp,D(op) if op is not None else p,D(high) if high is not None else p+1,D(low) if low is not None else p-1,p,D(10))


def snap(days=1,trend=False):
    start=END-days*86400;warm=start-WARMUP_4H*14400
    rows=[bar(warm+i*900,str(100+i/10) if trend else '100') for i in range((END-warm)//900)]
    return dict(symbol='BTCUSDT',source=SOURCE,start=start,end=END,warmup_start=warm,base_timeframe='15m',base_count=len(rows),bars=[b.data() for b in rows],excluded_forming=0,requested_count=len(rows),actual_common_coverage={'start':start,'end_exclusive':END},history_truncated=False)


def raw(b):return [b.time*1000,str(b.open),str(b.high),str(b.low),str(b.close),str(b.volume),(b.time+900)*1000-1]


def page_for(snapshot):
    rows=[raw(Bar.restore(b)) for b in snapshot['bars']]
    async def page(query):return [r for r in rows if query['startTime']<=r[0]<=query['endTime']][:query['limit']]
    return page


def config(**values):return Baseline(fee_bps='0',slippage_bps='0',**values)


def replay(side='LONG',next_price='102',high='103',low='99',baseline=None):
    rows=[bar(0),bar(900,next_price,high,low,op='100')]
    signal=[Decision(side,D(2),D(4),reason='REFERENCE'),Decision()]
    return simulate(rows,signal,0,2,900,baseline or config())


@pytest.mark.parametrize('side,price,pnl',[('LONG','102','40'),('LONG','99','-20'),('SHORT','99','20'),('SHORT','101','-20')])
def test_shared_long_short_reference_pnl(side,price,pnl):
    run=replay(side,price,high=str(max(D(100),D(price))+D('.5')),low=str(min(D(100),D(price))-D('.5')))
    assert D(run['metrics']['net_profit'])==D(pnl)
    assert D(run['metrics']['final_balance'])==10000+D(pnl)
    assert run['trades'][0]['entry_time']==900 and run['trades'][0]['signal_time']==900
    assert run['trades'][0]['entry_reason']=='REFERENCE'


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_fees_slippage_independent_rational_oracle(side):
    base=Baseline(fee_bps='10',slippage_bps='5')
    run=replay(side,'101',high='101.5',low='99',baseline=base);t=run['trades'][0]
    entry=F(100)*(1+(F(1,2000) if side=='LONG' else -F(1,2000)))
    exit_=F(101)*(1+(-F(1,2000) if side=='LONG' else F(1,2000)))
    size=F(t['size']);sign=1 if side=='LONG' else -1
    net=nearest_ticks(sign*(exit_-entry)*size)-ceiling_ticks(entry*size/F(1000))-ceiling_ticks(exit_*size/F(1000))
    assert F(t['entry_price'])==entry and F(t['exit_price'])==exit_
    assert F(t['realized_pnl'])*TICKS==net
    assert F(t['fees'])*TICKS==ceiling_ticks(entry*size/F(1000))+ceiling_ticks(exit_*size/F(1000))
    assert F(t['slippage_usdt'])*TICKS==nearest_ticks((abs(entry-100)+abs(exit_-101))*size)


@pytest.mark.parametrize('side,high,low,exit_price,reason',[
 ('LONG','105','97','98','STOP_LOSS_AMBIGUOUS'),('SHORT','103','95','102','STOP_LOSS_AMBIGUOUS'),
 ('LONG','105','99','104','TAKE_PROFIT'),('SHORT','101','95','96','TAKE_PROFIT')])
def test_same_candle_sl_tp_conservative(side,high,low,exit_price,reason):
    t=replay(side,'100',high,low)['trades'][0]
    assert D(t['exit_price'])==D(exit_price) and t['exit_reason']==reason


@pytest.mark.parametrize('side,gap,price,reason',[('LONG','90','90','STOP_GAP'),('SHORT','110','110','STOP_GAP'),
 ('LONG','110','104','TAKE_PROFIT_GAP_CONSERVATIVE'),('SHORT','90','96','TAKE_PROFIT_GAP_CONSERVATIVE')])
def test_protective_gap_before_scheduled_strategy_exit(side,gap,price,reason):
    rows=[bar(0),bar(900),bar(1800,gap)]
    signal=[Decision(side,D(2),D(4)),Decision(exit_long=True,exit_short=True),Decision()]
    t=simulate(rows,signal,0,3,900,config())['trades'][0]
    assert D(t['exit_price'])==D(price) and t['exit_reason']==reason


def test_position_sizing_risk_includes_slippage_and_fees():
    run=replay('LONG','101',high='102',low='99',baseline=Baseline(max_notional='10000'))
    t=run['trades'][0];entry=F(t['entry_price']);size=F(t['size']);planned_stop=F(t['stop_loss'])*F(1999,2000)
    risk=ceiling_ticks(abs(entry-planned_stop)*size)+ceiling_ticks(entry*size/F(1000))+ceiling_ticks(planned_stop*size/F(1000))
    assert risk<=100*TICKS and F(t['risk_usdt'])*TICKS==risk
    assert F(t['notional'])+F(t['entry_fee'])<=10000 and D(t['size']).as_tuple().exponent==-12


def test_precision_not_affected_by_external_decimal_context():
    reference=replay(baseline=Baseline())
    with localcontext() as ctx:
        ctx.prec=6
        assert replay(baseline=Baseline())==reference


def test_no_entry_from_prior_split_signal_or_development_cashflows():
    rows=[bar(i*900,str(100+i)) for i in range(6)]
    signal=[Decision('LONG',D(10),D(20))]+[Decision() for _ in range(5)]
    dev=simulate(rows,signal,0,3,900,config())
    validation=simulate(rows,signal,3,6,900,config())
    assert D(dev['metrics']['net_profit'])>0
    assert validation['trades']==[] and D(validation['metrics']['final_balance'])==10000


def test_preentry_range_cannot_trigger_stops():
    rows=[bar(0,'100',high='1000',low='1'),bar(900,'101',high='102',low='99',op='100')]
    result=simulate(rows,[Decision('LONG',D(2),D(4)),Decision()],0,2,900,config())
    assert result['trades'][0]['exit_reason']=='SEGMENT_END_CLOSE'
    assert result['trades'][0]['entry_time']==900


@pytest.mark.parametrize('name',list(PARAMETERS))
def test_signals_are_causal_future_perturbation_and_warmup(name):
    rows=[bar(i*900,str(100+i),str(D(100+i)+D('.5')),str(D(100+i)-D('.5'))) for i in range(320)]
    prefix=decisions(rows[:250],name)
    future=[bar((250+i)*900,str(100000+i),str(100100+i),'1') for i in range(70)]
    assert decisions(rows[:250]+future,name)[:250]==prefix
    assert all(d.direction is None for d in prefix[:20])
    assert any(d.direction=='LONG' for d in prefix[200:])
    signal=decisions(rows,name)
    assert simulate(rows,signal,210,250,900,config())==simulate(rows[:250],signal[:250],210,250,900,config())


@pytest.mark.parametrize('mutate,code',[
 (lambda rows:rows[:3]+rows[4:],'MISSING_CANDLES'),
 (lambda rows:rows[:3]+[rows[2]]+rows[3:],'DUPLICATE_OR_UNORDERED'),
 (lambda rows:[rows[1],rows[0]]+rows[2:],'DUPLICATE_OR_UNORDERED'),
 (lambda rows:[replace(rows[0],time=rows[0].time+1)]+rows[1:],'INVALID_TIMESTAMPS'),
 (lambda rows:[replace(rows[0],low=D(0))]+rows[1:],'INVALID_OHLCV'),
 (lambda rows:[replace(rows[0],volume=D('NaN'))]+rows[1:],'INVALID_OHLCV')])
def test_missing_duplicate_order_ohlcv_rejected(mutate,code):
    rows=[bar(i*900) for i in range(16)]
    with pytest.raises(LabError,match=code):validate_series(mutate(rows),900,14400)


def test_all_timeframes_same_common_calendar_and_split():
    report=execute(snap(),Baseline())
    assert report['split_at']%14400==0 and report['actual_development_pct'].startswith('66.666')
    for tf,c in report['coverage'].items():
        assert c['start']==END-86400 and c['end_exclusive']==END
        assert c['development_candles']*STEPS[tf]==report['split_at']-c['start']
        assert c['validation_candles']*STEPS[tf]==END-report['split_at']
    assert len(report['runs'])==24 and len([r for r in report['runs'] if r['status']=='INCOMPATIBLE'])==6
    assert all(r['metrics'] is None for r in report['runs'] if r['strategy']=='AURA_EXISTING')
    assert all(r['starting_balance']=='10000' for r in report['runs'] if r['status']=='OK')


def test_timeframe_aggregation_exact_prices_volume_no_partial_buckets():
    rows=[bar(i*900,str(100+i)) for i in range(16)]
    four=aggregate(rows,14400,14400)
    assert len(four)==1 and four[0].open==100 and four[0].close==115 and four[0].volume==160
    assert four[0].high==116 and four[0].low==99
    with pytest.raises(LabError):aggregate(rows[:-1],14400,14400)


def test_loader_excludes_forming_candle_and_records_full_count():
    snapshot=snap();real=page_for(snapshot)
    async def page(query):
        rows=await real(query)
        if rows and rows[-1][0]//1000+900==END:rows.append(raw(bar(END)))
        return rows
    result=asyncio.run(Loader(page,lambda:END+10).fetch(snapshot['start'],END))
    assert result['excluded_forming']==1 and result['base_count']==len(snapshot['bars'])
    assert result['bars'][-1]['time']+900==END and not result['history_truncated']


def test_loader_rejects_incomplete_without_silent_truncation():
    async def empty(query):return []
    with pytest.raises(LabError,match='INCOMPLETE_HISTORY'):asyncio.run(Loader(empty,lambda:END).fetch(END-86400,END))
    with pytest.raises(LabError,match='DATA_LIMIT'):asyncio.run(Loader(empty,lambda:END).fetch(END-90*86400,END))
    with pytest.raises(LabError,match='INVALID_RANGE'):asyncio.run(Loader(empty,lambda:END).fetch(END-86400+900,END))


def test_restart_snapshot_replay_reproducible_no_refetch(tmp_path):
    snapshot=snap(trend=True);cfg=Baseline();report=execute(snapshot,cfg)
    store=Store(tmp_path/'lab.sqlite3');ident=store.save(snapshot,cfg.data(),report)
    snap2,cfg2,report2=Store(store.path).load(ident)
    assert report2==report and execute(snap2,Baseline(**cfg2))==report
    assert Store(store.path).save(snapshot,cfg.data(),report)==ident
    async def run():
        service=Service(tmp_path,AsyncMock(side_effect=AssertionError('No refetch permitted')))
        service.store=Store(store.path)
        result=await service.replay(ident)
        assert result['replay_identical'] is True
    asyncio.run(run())


def test_snapshot_integrity_and_compression_bound(tmp_path):
    snapshot=snap();cfg=Baseline();report=execute(snapshot,cfg);store=Store(tmp_path/'lab.sqlite3');ident=store.save(snapshot,cfg.data(),report)
    import sqlite3,zlib
    with sqlite3.connect(store.path) as db:db.execute('UPDATE experiments SET report_hash=?',('bad',))
    with pytest.raises(LabError,match='CORRUPT_EXPERIMENT'):store.load(ident)
    with pytest.raises(LabError,match='CORRUPT_EXPERIMENT'):unpack(zlib.compress(b'{}')+b'trailer')


def test_lab_db_never_mutates_paper_or_archive_path(tmp_path):
    target=tmp_path/'paper.sqlite3';target.write_bytes(b'unchanged protected state')
    with pytest.raises(LabError,match='PATH_CONFLICT'):Store(target,forbidden=(target,)).list()
    alias=tmp_path/'alias.sqlite3';alias.symlink_to(target)
    with pytest.raises(LabError,match='PATH_CONFLICT'):Store(alias,forbidden=(target,)).list()
    assert target.read_bytes()==b'unchanged protected state'


def test_zero_trades_zero_losses_and_sharpe_undefined():
    zero=replay(baseline=config())
    assert zero['metrics']['profit_factor'] is None and zero['metrics']['average_loss'] is None
    rows=[bar(i*900) for i in range(10)]
    result=simulate(rows,[Decision() for _ in rows],0,10,900,config())
    m=result['metrics'];assert m['net_profit']=='0' and m['trades']==0 and m['win_rate'] is None and m['expectancy'] is None and m['sharpe'] is None
    assert m['sample_status']=='INCONCLUSIVE'


def test_compute_deadline_and_one_job_limit(tmp_path):
    import time
    with pytest.raises(LabError,match='COMPUTE_TIMEOUT'):execute(snap(),Baseline(),time.monotonic()-1)
    async def check():
        service=Service(tmp_path,AsyncMock())
        async with service.lock:
            with pytest.raises(LabError,match='BUSY'):await service.run({'days':1})
    asyncio.run(check())


def test_research_package_has_no_paper_private_client_execution_or_activation():
    root=Path(__file__).resolve().parents[1]/'app/lab'
    for path in root.glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=node.module or '' if isinstance(node,ast.ImportFrom) else ','.join(a.name for a in node.names)
                assert not any(s in names for s in ('paper','bybit','testnet','httpx','requests','socket'))
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('post','put','patch','delete'):
                assert isinstance(node.func.value,ast.Name) and node.func.value.id=='router'
    paths=app.openapi()['paths']
    assert {p for p,r in paths.items() if p.startswith('/api/lab') and 'post' in r}=={'/api/lab/run','/api/lab/experiments/{ident}/replay'}


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','dummy-lab-owner-password')
    monkeypatch.setenv('LAB_DB_PATH',str(tmp_path/'lab.sqlite3'))
    with TestClient(app) as c:
        app.state.lab=Service(tmp_path,page_for(snap()),lambda:END)
        yield c


def test_api_auth_csrf_preserves_paper_auto_and_no_activation(client):
    auth=('aura','dummy-lab-owner-password');headers={'X-Aura-Lab':'research-only','Origin':'http://testserver'}
    assert client.get('/api/lab/experiments').status_code==401
    assert client.post('/api/lab/run',auth=auth,json={'days':1}).status_code==403
    assert client.post('/api/lab/run',auth=auth,headers=headers,json={'days':1,'activate':True}).status_code==422
    before=client.get('/api/paper/state',auth=auth).json()
    result=client.post('/api/lab/run',auth=auth,headers=headers,json={'days':1})
    assert result.status_code==200 and result.json()['safety']['activation_available'] is False
    ident=result.json()['id'];after=client.get('/api/paper/state',auth=auth).json()
    assert before==after
    loaded=client.get('/api/lab/experiments/'+ident,auth=auth);assert loaded.json()==result.json()
    detail=client.get('/api/lab/experiments/'+ident+'/detail?timeframe=4h&split=validation&strategy=DONCHIAN',auth=auth).json()
    assert detail['limit']==100 and len(detail['equity_curve'])<=302
    assert client.post('/api/lab/experiments/'+ident+'/replay',auth=auth,headers=headers,json={}).json()['replay_identical']
    export=client.get('/api/lab/experiments/'+ident+'/export',auth=auth)
    assert export.headers['cache-control']=='no-store' and export.json()['snapshot']['source']==SOURCE


def test_target_that_loses_after_adverse_slippage_is_rejected():
    rows=[bar(0),bar(900,'100',high='100.01',low='99.99',op='100')]
    run=simulate(rows,[Decision('LONG',D(2),D('.001')),Decision()],0,2,900,Baseline(fee_bps='0',slippage_bps='100'))
    assert not run['trades'] and run['rejections']['TARGET_AFTER_COSTS']==1


def test_no_second_position_or_same_bar_entry_and_exit_signal_uses_next_open():
    rows=[bar(i*900,op='100') for i in range(6)]
    signals=[Decision('LONG',D(10),D(20)) for _ in rows]
    run=simulate(rows,signals,0,6,900,config())
    assert len(run['trades'])==1 and run['trades'][0]['exit_reason']=='SEGMENT_END_CLOSE'
    signals[2]=Decision(exit_long=True)
    run=simulate(rows,signals,0,6,900,config())
    assert run['trades'][0]['exit_time']==2700 and run['trades'][0]['exit_reason']=='STRATEGY_EXIT_NEXT_OPEN'


def test_sparse_daily_returns_and_constant_equity_do_not_claim_sharpe():
    baseline=Baseline();curve=[{'time':i*86400,'balance':'10000','equity':str(10000+i)} for i in range(40)]
    trades=[{'realized_pnl':'10','fees':'0','slippage_usdt':'0'}]
    assert metrics(trades,curve,baseline)['sharpe'] is None
    assert metrics(trades*20,[dict(p,equity='10000') for p in curve],baseline)['sharpe'] is None


def test_retention_keeps_newly_inserted_historical_study(tmp_path):
    snapshot=snap();report=execute(snapshot,Baseline());store=Store(tmp_path/'lab.sqlite3')
    ids=[]
    for i in range(12):
        config=Baseline(fee_bps=str(i)).data()
        row=dict(report,config=config)
        ids.append(store.save(snapshot,config,row))
    assert len(store.list())==10 and store.load(ids[-1])[2]['config']['fee_bps']=='11'
    with pytest.raises(LabError,match='EXPERIMENT_NOT_FOUND'):store.load(ids[0])


def test_lab_controls_do_not_enter_existing_pattern_validation_selector():
    html=(Path(__file__).resolve().parents[1]/'tests/fixtures/legacy_terminal.html').read_text()
    section=html.split('aria-labelledby="lab-title"',1)[1].split('<footer>',1)[0]
    assert 'class="pattern-controls"' not in section and 'class="lab-controls"' in section


def test_public_transport_response_size_is_bounded_get_only():
    from contextlib import asynccontextmanager
    from app.lab.data import public_page
    calls=[]
    class Reply:
        def raise_for_status(self):pass
        async def aiter_bytes(self):yield b'x'*1000001
    class Client:
        @asynccontextmanager
        async def stream(self,method,url,params):
            calls.append((method,url,params));yield Reply()
    with pytest.raises(LabError,match='PUBLIC_DATA_UNAVAILABLE'):asyncio.run(public_page(Client(),{'symbol':'BTCUSDT'}))
    assert calls[0][0]=='GET' and calls[0][1]=='https://data-api.binance.vision/api/v3/klines'
