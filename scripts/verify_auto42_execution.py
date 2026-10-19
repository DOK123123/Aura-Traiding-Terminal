"""TEST ONLY: deterministic production Service/SQLite/engine verification.

Never reads runtime credentials or production configuration; uses temporary stores.
Synthetic market contexts here prove plumbing/accounting, never strategy performance.
"""
import asyncio
from copy import deepcopy
from decimal import Decimal as D, ROUND_CEILING, ROUND_HALF_EVEN, localcontext
from pathlib import Path
import tempfile
from unittest.mock import patch

from app.automated.engine import initial,event,DemoError,POLICY,validate
from app.automated.service import Service
from app.automated.storage import SQLiteStore
from app.automated.strategy import strategy
from app.intelligence.market_context import SOURCE
from app.lab.models import Bar,digest
from research.market_intelligence.structure import VERSION

START=1700000000//14400*14400

def bar(t,o='100',h='101',l='99',c='100'):
    return Bar(t,*map(D,(o,h,l,c,'100')))

class TestMarket:
    """Fabricated context ONLY for isolated execution tests, never live/replay."""
    __test__=False
    def __init__(self,side):
        self.side=side;self.bars=[bar(START+i*900) for i in range(300)];self.signal=True;self.failure=None
    async def snapshot(self,tf):
        if self.failure:raise DemoError(self.failure)
        at=self.bars[-1].time+900;d=1 if self.side=='LONG' else -1
        return dict(status='OK',freshness=dict(status='FRESH'),source=SOURCE,symbol='BTCUSDT',timeframe='15m',last_closed_at=at,
            history=dict(source_sha256=digest([b.data() for b in self.bars])),
            state=dict(version=VERSION,timestamp=at,timeframe='15m',symbol='BTCUSDT',
                mtf=dict(known_mask=3,alignment=True,h1=dict(direction=d,closed_at=at//3600*3600),h4=dict(direction=d,closed_at=at//14400*14400)),
                trend_direction=d,trend_strength=30,retest=self.side if self.signal else None,retest_origin=dict(direction=self.side,level='99.5' if d==1 else '100.5',breakout_closed_at=at-900),liquidity_sweep=None,atr=1,volatility_ratio=1,
                support='80',resistance='120',breakout_level='99.5' if d==1 else '100.5',regime='TREND_UP' if d==1 else 'TREND_DOWN'),
            structure_events=[dict(type='structure_event',value='BOS',confirmed_at=at-900),dict(type='breakout',value=self.side,confirmed_at=at-900)])
    def add(self,**kw):self.bars.append(bar(self.bars[-1].time+900,**kw))

async def seed_store(path,now,epoch):
    store=SQLiteStore(path,clock=lambda:now[0]);env=await store.load();s=initial(now[0],epoch=epoch)
    e=event(s,'TEST_ONLY',0,now[0],dict(reason='TEST_ONLY_ISOLATED'))
    await store.commit(env['revision'],s,[e],e['id']);return store

def rounded(x,up=False):return x.quantize(D('.00000001'),rounding=ROUND_CEILING if up else ROUND_HALF_EVEN)

def check_accounting(position,closed,state):
    """Independent Decimal oracle; not production fee/fill implementations."""
    with localcontext() as ctx:
        ctx.prec=64
        q=D(position['size']);long=position['direction']=='LONG';sign=1 if long else -1
        entry=D(position['entry_raw_price'])*(D('1.0005') if long else D('.9995'))
        exit=D(closed['exit_raw_price'])*(D('.9995') if long else D('1.0005'))
        ef=rounded(entry*q*D('.001'),True);xf=rounded(exit*q*D('.001'),True)
        gross=rounded(sign*(exit-entry)*q);net=rounded(gross-ef-xf)
        assert D(position['entry_price'])==entry and D(closed['exit_price'])==exit
        assert D(position['entry_fee'])==ef and D(closed['exit_fee'])==xf
        assert D(closed['realized_pnl'])==net
        assert D(state['balance'])==D(10000)+net
        assert D(state['fees'])==ef+xf
        slip=rounded(rounded(abs(entry-D(position['entry_raw_price']))*q)+abs(exit-D(closed['exit_raw_price']))*q)
        assert D(state['slippage'])==slip
        assert D(position['risk_usdt'])<=D(50) and D(position['notional'])<=D(2000)

async def lifecycle(side,exit_kind):
    market=TestMarket(side);now=[market.bars[-1].time+930]
    with tempfile.TemporaryDirectory(prefix='aura-test-only-') as folder:
        path=Path(folder)/'auto-paper-42.sqlite3';store=await seed_store(path,now,'TEST_ONLY_'+side+'_'+exit_kind)
        svc=Service(market,store,clock=lambda:now[0])
        try:
            with patch('app.automated.service.scheduler_configured',return_value=True):
                started=await svc.control('START','a'*32);assert started['state']['mode']=='ON'
                market.add();now[0]+=900;await svc.tick();assert (await store.load())['state']['pending']
                market.add();now[0]+=900
                other=Service(market,SQLiteStore(path,clock=lambda:now[0]),clock=lambda:now[0])
                try:await asyncio.gather(svc.tick(),other.tick())
                finally:await other.close()
                position=deepcopy((await store.load())['state']['position']);assert position
                assert sum(e['kind']=='OPEN' for e in await store.history())==1
                await svc.close()
                # Reconstruct store and controller, as a fresh process would; no in-memory portfolio reused.
                store=SQLiteStore(path,clock=lambda:now[0]);svc=Service(market,store,clock=lambda:now[0])
                restored=(await store.load())['state']
                assert restored['position']==position and restored['mode']=='ON'
                await svc.tick();assert sum(e['kind']=='OPEN' for e in await store.history())==1
                market.signal=False;stop=D(position['stop_loss']);target=D(position['take_profit'])
                high=max(D(101),target+1) if exit_kind in ('TP','BOTH') or side=='SHORT' and exit_kind=='SL' else D(101)
                low=min(D(99),target-1) if side=='SHORT' and exit_kind=='TP' else min(D(99),stop-1) if side=='LONG' and exit_kind in ('SL','BOTH') else D(99)
                if side=='SHORT' and exit_kind=='SL':high=stop+1
                market.add(h=str(high),l=str(low));now[0]+=900;await svc.tick();await svc.tick()
                env=await store.load();state=env['state'];validate(state)
                journal=await store.history();closed=[e['payload'] for e in journal if e['kind']=='CLOSE']
                assert len(closed)==1 and state['position'] is None
                expected='STOP_LOSS_AMBIGUOUS' if exit_kind=='BOTH' else 'TAKE_PROFIT' if exit_kind=='TP' else 'STOP_LOSS'
                assert closed[0]['exit_reason']==expected,(side,exit_kind,closed[0]['exit_reason'])
                check_accounting(position,closed[0],state)
                return dict(label='TEST ONLY — SYNTHETIC CONTEXT',direction=side,scenario=exit_kind,status='PASS',
                    persisted_open=position,closed_trade=closed[0],final_balance=state['balance'],fees=state['fees'],
                    slippage=state['slippage'],revision=env['revision'],opened=1,closed=1,
                    restart_restored=True,concurrent_duplicate_prevented=True)
        finally:await svc.close()

async def controls():
    market=TestMarket('LONG');now=[market.bars[-1].time+930]
    with tempfile.TemporaryDirectory(prefix='aura-test-only-controls-') as folder:
        store=await seed_store(Path(folder)/'auto-paper-42.sqlite3',now,'TEST_ONLY_CONTROLS');svc=Service(market,store,clock=lambda:now[0])
        checks=[]
        try:
            with patch('app.automated.service.scheduler_configured',return_value=True):
                await svc.control('START','1'*32)
                for error in ('STALE_DATA','MISSING_CANDLES'):
                    market.failure=error;now[0]+=300;await svc.tick();s=(await store.load())['state']
                    assert s['position'] is None and s['balance']=='10000' and s['mode']=='PAUSED';checks.append(error)
                    market.failure=None
                    if error=='STALE_DATA':
                        now[0]+=300;await svc.tick();assert (await store.load())['state']['mode']=='ON';checks.append('FRESH_DATA_RECOVERY')
                await svc.control('STOP','2'*32);now[0]+=300;await svc.tick();s=(await store.load())['state']
                assert s['mode']=='OFF' and s['position'] is None;checks.append('STOP')
                await svc.control('EMERGENCY','3'*32);now[0]+=300;await svc.tick();s=(await store.load())['state']
                assert s['mode']=='EMERGENCY' and s['emergency'];checks.append('EMERGENCY')
                try:await svc.control('START','4'*32)
                except DemoError as e:assert e.code=='EMERGENCY_RESET_REQUIRED';checks.append('EMERGENCY_BLOCKS_START')
                else:raise AssertionError('Emergency START accepted')
            return dict(status='PASS',checks=checks,balance=s['balance'],opened=0)
        finally:await svc.close()

async def run():
    if not __debug__:raise RuntimeError('VERIFICATION_REQUIRES_ASSERTIONS')
    cases=[]
    for side in ('LONG','SHORT'):
        for kind in ('TP','SL'):cases.append(await lifecycle(side,kind))
    cases.append(await lifecycle('LONG','BOTH'))
    return dict(status='PASS',evidence_type='ISOLATED_TECHNICAL_TEST',test_only=True,
                storage='TEMPORARY_SQLITE_PRODUCTION_STORE',supabase_integration='NOT_TESTED',
                strategy_input='DETERMINISTIC_SYNTHETIC_CONTEXT_NOT_MARKET_EVIDENCE',policy=POLICY,
                cases=cases,controls=await controls(),live_autonomy='NOT_TESTED')

if __name__=='__main__':
    import json
    print(json.dumps(asyncio.run(run()),ensure_ascii=False,indent=2))
