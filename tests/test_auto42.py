"""Synthetic algorithm fixtures only; never market profitability evidence."""
import asyncio,json,logging,sqlite3,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from decimal import Decimal as D
from unittest.mock import patch
import httpx
from fastapi import FastAPI
from app.lab.models import Bar,digest,money
from app.automated.engine import (initial,advance,open_virtual,close_virtual,protective,mark,
    risk_reason,DemoError,validate,liquidation_equity,POLICY)
from app.automated.strategy import strategy
from app.automated.storage import SQLiteStore,SupabaseStore,packed
from app.automated.service import Service,configured
from app.automated.api import router
from app.intelligence.market_context import SOURCE
from research.market_intelligence.structure import VERSION

DUMMY_TOKEN='dummy-auto42-scheduler-for-unit-tests-only-00000'
DUMMY_OWNER='dummy-owner-for-unit-tests-only'
DUMMY_KEY='dummy-supabase-for-unit-tests-only-00000'


def bar(t,open='100',high='101',low='99',close='100'):
    return Bar(t,D(open),D(high),D(low),D(close),D(100))


def fixture(side='LONG'):
    start=1700000000//14400*14400;bs=[bar(start+i*900) for i in range(300)];at=bs[-1].time+900
    trend=1 if side=='LONG' else -1
    state=dict(version=VERSION,timestamp=at,timeframe='15m',symbol='BTCUSDT',mtf=dict(known_mask=3,alignment=True,
        h1=dict(direction=trend,closed_at=at//3600*3600),h4=dict(direction=trend,closed_at=at//14400*14400)),
        trend_direction=trend,trend_strength=30,retest=side,liquidity_sweep=None,atr=1,volatility_ratio=1,
        support='80',resistance='120',breakout_level='99.5' if trend==1 else '100.5',regime='TREND_UP' if trend==1 else 'TREND_DOWN')
    snap=dict(status='OK',freshness=dict(status='FRESH'),source=SOURCE,symbol='BTCUSDT',timeframe='15m',last_closed_at=at,state=state,
        history=dict(source_sha256=digest([b.data() for b in bs])),structure_events=[
            dict(type='structure_event',value='BOS',confirmed_at=at-900),dict(type='breakout',value=side,confirmed_at=at-900)])
    return bs,snap,[at+30]


class Market:
    def __init__(self,bs,snap):self.bars=bs;self.value=snap;self.reads=0
    async def snapshot(self,tf):self.reads+=1;return deepcopy(self.value)


class StrategyTests(unittest.TestCase):
    def test_deterministic_long_short_and_no_analog_dependency(self):
        for side in ('LONG','SHORT'):
            bs,snap,now=fixture(side);a=strategy(snap,bs,now[0]);self.assertEqual(a,strategy(snap,bs,now[0]))
            self.assertEqual(a['direction'],side);self.assertIn('NO_EDGE_FOUND',a['classification'])
            snap['analog_availability']=dict(status='NO_EDGE_FOUND',fake_probability=.99)
            self.assertEqual(a,strategy(snap,bs,now[0]))
    def test_no_setup_wait_and_mtf_alignment_filter(self):
        bs,snap,now=fixture();snap['state']['retest']=None;self.assertIsNone(strategy(snap,bs,now[0])['direction'])
        snap['state']['mtf']['alignment']=False;self.assertEqual(strategy(snap,bs,now[0])['reason'],'MTF_NOT_ALIGNED')
    def test_opposing_liquidity_and_levels_reject(self):
        bs,snap,now=fixture();snap['state']['liquidity_sweep']='SHORT';self.assertEqual(strategy(snap,bs,now[0])['reason'],'OPPOSING_LIQUIDITY')
        snap['state']['liquidity_sweep']=None;snap['state']['resistance']='102';self.assertEqual(strategy(snap,bs,now[0])['reason'],'OPPOSING_LEVEL_TOO_CLOSE')
    def test_closed_timeframes_and_future_pivots_never_confirm(self):
        bs,snap,now=fixture();snap['state']['mtf']['h4']['closed_at']=now[0]+14400
        with self.assertRaisesRegex(DemoError,'MTF_UNAVAILABLE'):strategy(snap,bs,now[0])
        bs,snap,now=fixture();snap['structure_events'][0]['confirmed_at']=now[0]+900
        self.assertEqual(strategy(snap,bs,now[0])['reason'],'NO_CONFIRMED_STRUCTURE_BREAK')
        bs.append(bar(bs[-1].time+900))
        with self.assertRaises(DemoError):strategy(snap,bs,now[0])
    def test_actual_structure_prefix_invariance_and_confirmed_pivots(self):
        from tests.test_market_intelligence import bars
        from research.market_intelligence.structure import segment_states
        bs=bars(450);before=segment_states(bs[:400]);after=segment_states(bs)
        self.assertEqual(before,after[:400])
        for row in before:
            if row:
                for p in row['confirmed_pivots']:
                    self.assertLess(p['pivot_time'],p['confirmation_time'])
                    self.assertLessEqual(p['confirmation_time'],row['timestamp'])
    def test_malformed_candles_and_portfolio_are_sanitized(self):
        bs,snap,now=fixture();bs[-1]=bar(bs[-1].time,low='105')
        with self.assertRaisesRegex(DemoError,'INVALID_MARKET_DATA'):strategy(snap,bs,now[0])
        for state in ({},None,initial(now[0])|{'balance':'NaN'}):
            with self.assertRaises(DemoError):validate(state)
    def test_invalid_indicator_numbers_do_not_create_signal(self):
        for value in (float('nan'),float('inf'),True,None):
            bs,snap,now=fixture();snap['state']['trend_strength']=value
            with self.assertRaises(DemoError):strategy(snap,bs,now[0])
    def test_stale_source_snapshot_and_gap_reject(self):
        for change in ('stale','source','hash','gap'):
            bs,snap,now=fixture()
            if change=='stale':snap['freshness']['status']='STALE'
            elif change=='source':snap['source']='OtherExchange'
            elif change=='hash':snap['history']['source_sha256']='wrong'
            else:bs.pop(-20);snap['history']['source_sha256']=digest([b.data() for b in bs])
            with self.assertRaises(DemoError):strategy(snap,bs,now[0])


class MathTests(unittest.TestCase):
    def plan(self,side='LONG',at=900):return dict(direction=side,stop_loss='98' if side=='LONG' else '102',take_profit='104' if side=='LONG' else '96',signal_at=at,reason='UNIT_FIXTURE',source=SOURCE)
    def opened(self,side='LONG'):
        s=initial(900,epoch='unit-epoch');s['mode']='ON';open_virtual(s,self.plan(side),bar(900),1800);return s
    def test_long_short_profit_loss_and_independent_accounting(self):
        for side in ('LONG','SHORT'):
            for price in ('95','105'):
                s=self.opened(side);p=deepcopy(s['position']);e=close_virtual(s,D(price),2700,'TEST_CLOSE')['payload']
                q=D(p['size']);entry=D(p['entry_price']);exit=D(price)*(D('.9995') if side=='LONG' else D('1.0005'))
                gross=money((exit-entry)*q*(1 if side=='LONG' else -1));net=money(gross-D(p['entry_fee'])-D(e['exit_fee']))
                self.assertEqual(D(e['realized_pnl']),net);self.assertEqual(D(s['balance']),D(10000)+net)
                self.assertEqual(D(e['exit_price']),exit);self.assertEqual(s['trades'],1);self.assertEqual(s['wins'],int(net>0))
    def test_money_results_do_not_depend_on_callers_decimal_context(self):
        from decimal import localcontext
        s=self.opened();mark(s,bar(1800,close='100.123456789'),2700);e=close_virtual(s,D('101.123456789'),3600,'TEST')
        with localcontext() as ctx:
            ctx.prec=6
            other=self.opened();mark(other,bar(1800,close='100.123456789'),2700);f=close_virtual(other,D('101.123456789'),3600,'TEST')
            validate(other)
        self.assertEqual(s,other);self.assertEqual(e,f)
    def test_fee_inclusive_sizing_risk_notional_and_precision(self):
        s=self.opened();p=s['position'];q=D(p['size']);entry=D(p['entry_price']);stop=D(p['stop_loss'])*D('.9995')
        worst=(entry-stop)*q+(entry+stop)*q*D('.001')
        self.assertLessEqual(worst,D(50));self.assertLessEqual(D(p['notional']),2000)
        self.assertEqual(entry,D('100.0500'));self.assertEqual(q,q.quantize(D('.000000000001')))
        self.assertLessEqual(D(p['risk_usdt']),D(p['risk_budget_usdt']))
    def test_stop_target_ambiguous_and_gaps_long_short(self):
        for side in ('LONG','SHORT'):
            for scenario in ('SL','TP','BOTH','STOP_GAP','TP_GAP'):
                s=self.opened(side)
                vals={'SL':('100','101','97') if side=='LONG' else ('100','103','99'),
                    'TP':('100','105','99') if side=='LONG' else ('100','101','95'),
                    'BOTH':('100','105','97') if side=='LONG' else ('100','103','95'),
                    'STOP_GAP':('95','97','94') if side=='LONG' else ('105','106','104'),
                    'TP_GAP':('106','107','105') if side=='LONG' else ('94','95','93')}[scenario]
                b=bar(1800,*vals,close=vals[0]);e=protective(s,b,2700)['payload'];self.assertIsNone(s['position'])
                expected={'SL':'STOP_LOSS','TP':'TAKE_PROFIT','BOTH':'STOP_LOSS_AMBIGUOUS','STOP_GAP':'STOP_GAP','TP_GAP':'TAKE_PROFIT_GAP_CONSERVATIVE'}[scenario]
                self.assertEqual(e['exit_reason'],expected)
                if scenario=='STOP_GAP':self.assertEqual(D(e['exit_raw_price']),D(vals[0]))
                if scenario=='TP_GAP':self.assertEqual(D(e['exit_raw_price']),D('104' if side=='LONG' else '96'))
    def test_daily_loss_and_drawdown_latch_protective_only(self):
        s=initial(900);s.update(mode='ON',day_low_equity='9800',equity='9800');self.assertEqual(risk_reason(s),'DAILY_LOSS_LIMIT')
        with self.assertRaisesRegex(DemoError,'DAILY_LOSS_LIMIT'):open_virtual(s,self.plan(),bar(900),1800)
        s.update(day_low_equity='10000',max_drawdown_pct='10');self.assertEqual(risk_reason(s),'DRAWDOWN_LIMIT')
        with self.assertRaisesRegex(DemoError,'DRAWDOWN_LIMIT'):open_virtual(s,self.plan(),bar(900),1800)
    def test_insufficient_balance_position_cap_invalid_stops(self):
        s=self.opened()
        with self.assertRaisesRegex(DemoError,'POSITION_LIMIT'):open_virtual(s,self.plan(),bar(900),1800)
        s=initial(900);s.update(mode='ON',balance='0',equity='0')
        with self.assertRaises(DemoError):open_virtual(s,self.plan(),bar(900),1800)
        s=initial(900);s['mode']='ON';bad=self.plan();bad['stop_loss']='101'
        with self.assertRaisesRegex(DemoError,'INVALID_STOPS'):open_virtual(s,bad,bar(900),1800)
    def test_next_open_no_signal_bar_intrabar_execution(self):
        bs,snap,now=fixture();s=initial(now[0]);s['mode']='ON';s,_=advance(s,bs,strategy(snap,bs,now[0]),now[0]);self.assertIsNone(s['pending'])
        b=bar(bs[-1].time+900);bs.append(b);now[0]+=900;snap['state']['timestamp']+=900;snap['last_closed_at']+=900
        d=dict(self.plan(at=bs[-1].time+900));s,events=advance(s,bs,d,now[0]);self.assertIsNone(s['position']);self.assertIsNotNone(s['pending'])
        signal_at=s['pending']['signal_at'];bs.append(bar(bs[-1].time+900,open='101',high='102',low='100',close='101'));now[0]+=900
        s,events=advance(s,bs,dict(direction=None,reason='WAIT'),now[0]);self.assertEqual(s['position']['entry_time'],signal_at)
        self.assertEqual(D(s['position']['entry_price']),D('101.0505'))
        s2,events2=advance(s,bs,dict(direction=None,reason='WAIT'),now[0]);self.assertEqual(s,s2);self.assertEqual(events2,[])
    def test_missed_candle_cancels_pending_no_backfill(self):
        bs,snap,now=fixture();s=initial(now[0]);s['mode']='ON';s,_=advance(s,bs,{},now[0]);s['pending']=self.plan(at=s['watermark'])
        bs += [bar(bs[-1].time+900),bar(bs[-1].time+1800)];now[0]+=1800
        s,events=advance(s,bs,dict(direction=None,reason='WAIT'),now[0]);self.assertIsNone(s['position']);self.assertEqual(s['missed_candles'],1)
        self.assertTrue(any(e['kind']=='MISSED' for e in events))
    def test_unknown_gap_and_correction_do_not_invent_exit(self):
        bs,snap,now=fixture();s=initial(now[0]);s['mode']='ON';s,_=advance(s,bs,{},now[0])
        old=deepcopy(s);bs += [bar(bs[-1].time+1800)];now[0]+=1800
        with self.assertRaisesRegex(DemoError,'MISSING_CANDLES'):advance(s,bs,{},now[0])
        self.assertEqual(old,s)
        bs,snap,now=fixture();s=initial(now[0]);s['mode']='ON';s,_=advance(s,bs,{},now[0]);bs[-1]=bar(bs[-1].time,close='100.5')
        with self.assertRaisesRegex(DemoError,'SOURCE_CORRECTION'):advance(s,bs,{},now[0])
    def test_stop_and_emergency_preserve_protective_exit(self):
        s=self.opened();s.update(mode='EMERGENCY',emergency=True)
        self.assertEqual(risk_reason(s),'EMERGENCY_STOP');self.assertIsNotNone(protective(s,bar(1800,high='105'),2700))
    def test_liquidation_equity_includes_exit_costs(self):
        s=self.opened();p=s['position'];px=D(100)*D('.9995');q=D(p['size'])
        from app.lab.execution import fee
        expected=money(D(s['balance'])+money((px-D(p['entry_price']))*q)-fee(px,q,D('.001')))
        self.assertEqual(liquidation_equity(s,D(100)),expected)


class StoreServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.bs,self.snap,self.now=fixture();self.market=Market(self.bs,self.snap)
        self.path=Path(self.folder.name)/'auto-paper-42.sqlite3';self.store=SQLiteStore(self.path,clock=lambda:self.now[0]);self.svc=Service(self.market,self.store,clock=lambda:self.now[0])
    async def asyncTearDown(self):await self.svc.close();self.folder.cleanup()
    def auth(self):return patch.dict('os.environ',AURA_AUTO42_SCHEDULER_SECRET=DUMMY_TOKEN,AURA_TESTNET_VIEW_PASSWORD=DUMMY_OWNER)
    async def test_defaults_off_and_no_market_fetch_or_entry_on_load(self):
        self.assertEqual((await self.store.load())['state']['mode'],'OFF');await self.svc.dashboard();self.assertEqual(self.market.reads,0)
        await self.svc.tick();self.assertEqual(self.market.reads,0);self.assertEqual((await self.store.load())['state']['balance'],'10000')
    async def test_explicit_start_duplicate_run_and_restart(self):
        with self.auth():
            a=await self.svc.control('START','a'*32);self.assertEqual(a['state']['mode'],'ON')
            b=await self.svc.control('START','a'*32);self.assertTrue(b['duplicate'])
            await asyncio.gather(self.svc.tick(),self.svc.tick());count=len(await self.store.history())
            fresh=Service(self.market,SQLiteStore(self.path,clock=lambda:self.now[0]),clock=lambda:self.now[0]);self.assertTrue((await fresh.tick())['duplicate'])
            self.assertEqual(len(await self.store.history()),count);await fresh.close()
    async def test_scheduler_unconfigured_activation_rejected(self):
        with self.assertRaisesRegex(DemoError,'SCHEDULER_NOT_CONFIGURED'):await self.svc.control('START','a'*32)
    async def test_compare_swap_concurrency_and_atomic_rollback(self):
        loaded=await self.store.load();s=loaded['state'];e=dict(id='test',kind='TEST',epoch=s['epoch'],created_at=self.now[0],payload=dict(execution_mode='PAPER_ONLY',real_money_execution='DISABLED'))
        await self.store.commit(loaded['revision'],s,[e],'test')
        with self.assertRaisesRegex(DemoError,'CONCURRENT_UPDATE'):await self.store.commit(loaded['revision'],s,[dict(e,id='other')],'other')
        n=await self.store.load()
        with self.assertRaises(DemoError):await self.store.commit(n['revision'],s,[dict(e,id='bad',payload={})],'bad')
        self.assertEqual((await self.store.load())['revision'],n['revision'])
    async def test_durable_pending_and_single_entry_after_restart(self):
        with self.auth():await self.svc.control('START','a'*32)
        # Commit a signal when a NEW closed candle is available.
        self.add_bar();await self.svc.tick();s=(await self.store.load())['state'];self.assertIsNotNone(s['pending'])
        restarted=Service(self.market,SQLiteStore(self.path,clock=lambda:self.now[0]),clock=lambda:self.now[0]);self.add_bar()
        await restarted.tick();await restarted.tick();s=(await self.store.load())['state'];self.assertIsNotNone(s['position'])
        events=await self.store.history();self.assertEqual(sum(e['kind']=='OPEN' for e in events),1);await restarted.close()
    def add_bar(self):
        self.bs.append(bar(self.bs[-1].time+900));self.now[0]+=900;at=self.bs[-1].time+900
        v=self.market.value;v['last_closed_at']=at;v['state']['timestamp']=at;v['history']['source_sha256']=digest([b.data() for b in self.bs])
        for key,step in [('h1',3600),('h4',14400)]:v['state']['mtf'][key]['closed_at']=at//step*step
        v['structure_events']=[dict(type='structure_event',value='BOS',confirmed_at=at-900),dict(type='breakout',value='LONG',confirmed_at=at-900)]
    async def test_full_virtual_signal_entry_exit_commission_journal(self):
        with self.auth():await self.svc.control('START','a'*32)
        self.add_bar();await self.svc.tick();self.add_bar();await self.svc.tick()
        before=(await self.store.load())['state'];self.assertIsNotNone(before['position'])
        target=D(before['position']['take_profit']);self.add_bar()
        last=self.bs[-1];self.bs[-1]=bar(last.time,high=str(target+1),close='100')
        self.market.value['history']['source_sha256']=digest([b.data() for b in self.bs]);self.market.value['state']['retest']=None
        await self.svc.tick();s=(await self.store.load())['state'];self.assertIsNone(s['position']);self.assertEqual(s['trades'],1)
        self.assertGreater(D(s['realized_pnl']),0);self.assertEqual(D(s['balance']),D(10000)+D(s['realized_pnl']))
        events=await self.store.history();self.assertEqual(sum(e['kind']=='CLOSE' for e in events),1)
        self.assertGreater(D(s['fees']),0);self.assertGreater(D(s['slippage']),0)
    async def test_concurrent_instances_never_double_entry(self):
        with self.auth():await self.svc.control('START','a'*32)
        self.add_bar();await self.svc.tick();self.add_bar()
        other=Service(self.market,SQLiteStore(self.path,clock=lambda:self.now[0]),clock=lambda:self.now[0])
        await asyncio.gather(self.svc.tick(),other.tick())
        self.assertEqual(sum(e['kind']=='OPEN' for e in await self.store.history()),1);await other.close()
    async def test_stop_wins_against_inflight_start(self):
        original=self.market.snapshot;began=asyncio.Event();release=asyncio.Event()
        async def delayed(tf):began.set();await release.wait();return await original(tf)
        self.market.snapshot=delayed
        with self.auth():
            start=asyncio.create_task(self.svc.control('START','a'*32));await began.wait()
            await self.svc.control('STOP','b'*32);release.set()
            with self.assertRaisesRegex(DemoError,'CONCURRENT_UPDATE'):await start
        self.assertEqual((await self.store.load())['state']['mode'],'OFF')
    async def test_delayed_start_after_stop_requires_current_revision(self):
        old=(await self.store.load())['revision'];await self.svc.control('STOP','b'*32)
        with self.auth(),self.assertRaisesRegex(DemoError,'CONCURRENT_UPDATE'):
            await self.svc.control('START','a'*32,expected_revision=old)
        self.assertEqual((await self.store.load())['state']['mode'],'OFF')
    async def test_emergency_during_pending_tick_cancels_entry(self):
        with self.auth():await self.svc.control('START','a'*32)
        self.add_bar();await self.svc.tick();self.add_bar()
        original=self.market.snapshot;began=asyncio.Event();release=asyncio.Event()
        async def delayed(tf):began.set();await release.wait();return await original(tf)
        self.market.snapshot=delayed;t=asyncio.create_task(self.svc.tick());await began.wait()
        await self.svc.control('EMERGENCY','b'*32);release.set();await t
        s=(await self.store.load())['state'];self.assertEqual(s['mode'],'EMERGENCY');self.assertIsNone(s['position']);self.assertIsNone(s['pending'])
    async def test_mtf_analysis_failure_does_not_block_known_protective_exit(self):
        with self.auth():await self.svc.control('START','a'*32)
        self.add_bar();await self.svc.tick();self.add_bar();await self.svc.tick()
        s=(await self.store.load())['state'];stop=D(s['position']['stop_loss']);self.add_bar()
        self.bs[-1]=bar(self.bs[-1].time,low=str(stop-1));self.market.value['history']['source_sha256']=digest([b.data() for b in self.bs])
        self.market.value['state']['mtf']['h4']=None
        r=await self.svc.tick();self.assertEqual(r['status'],'PAUSED');s=(await self.store.load())['state']
        self.assertIsNone(s['position']);self.assertEqual(s['trades'],1);self.assertEqual(s['last_error'],'MTF_UNAVAILABLE')
    async def test_risk_limit_persists_restart_and_cannot_be_rearmed(self):
        envelope=await self.store.load();s=envelope['state'];s.update(balance='9800',equity='9800',day_low_equity='9800',realized_pnl='-200',gross_loss='200',trades=1,losses=1,mode='PAUSED')
        e=dict(id='unit-loss',kind='TEST',epoch=s['epoch'],created_at=self.now[0],payload=dict(execution_mode='PAPER_ONLY',real_money_execution='DISABLED'))
        await self.store.commit(envelope['revision'],s,[e],'unit-loss')
        reopened=Service(self.market,SQLiteStore(self.path,clock=lambda:self.now[0]),clock=lambda:self.now[0])
        with self.auth(),self.assertRaisesRegex(DemoError,'DAILY_LOSS_LIMIT'):await reopened.control('START','a'*32)
        await reopened.close()
    async def test_reset_open_position_rejected_history_unchanged(self):
        with self.auth():await self.svc.control('START','a'*32)
        self.add_bar();await self.svc.tick();self.add_bar();await self.svc.tick();await self.svc.control('STOP','b'*32)
        before=await self.store.history()
        with self.assertRaisesRegex(DemoError,'RESET_BLOCKED_OPEN_POSITION'):await self.svc.control('RESET','c'*32)
        self.assertEqual(before,await self.store.history())
    async def test_corrupted_persisted_account_fails_without_reset(self):
        with sqlite3.connect(self.path) as c:c.execute("update auto42_account set payload='{}'")
        with self.assertRaisesRegex(DemoError,'CORRUPT_PORTFOLIO'):await self.svc.dashboard()
        with sqlite3.connect(self.path) as c:self.assertEqual(c.execute('select payload from auto42_account').fetchone()[0],'{}')
    async def test_remote_success_contract_and_network_scope(self):
        s=initial(self.now[0]);seen=[]
        def handle(r):
            seen.append(r);self.assertEqual(r.url.host,'abcdefghijklmnopqrst.supabase.co');self.assertEqual(r.method,'POST')
            self.assertEqual(r.headers['apikey'],DUMMY_KEY)
            return httpx.Response(200,json=dict(packed(s),revision=1))
        store=SupabaseStore('https://abcdefghijklmnopqrst.supabase.co',DUMMY_KEY,httpx.MockTransport(handle))
        result=await store.load();self.assertEqual(result['state'],s);self.assertEqual(len(seen),1);await store.close()
    async def test_error_pause_no_watermark_advance(self):
        with self.auth():await self.svc.control('START','a'*32)
        old=(await self.store.load())['state']['watermark'];self.add_bar();self.market.value['status']='STALE'
        r=await self.svc.tick();self.assertEqual(r['status'],'PAUSED');s=(await self.store.load())['state']
        self.assertEqual(s['watermark'],old);self.assertEqual(s['mode'],'PAUSED');self.assertIsNone(s['pending'])
    async def test_emergency_restart_and_reset_archives_history(self):
        with self.auth():await self.svc.control('START','a'*32)
        await self.svc.control('EMERGENCY','b'*32)
        with self.auth(),self.assertRaisesRegex(DemoError,'EMERGENCY_RESET_REQUIRED'):await self.svc.control('START','c'*32)
        before=await self.store.history();epoch=(await self.store.load())['state']['epoch'];await self.svc.control('RESET','d'*32)
        self.assertNotEqual((await self.store.load())['state']['epoch'],epoch);self.assertGreater(len(await self.store.history()),len(before))
        self.assertTrue(any('archived_account' in e['payload'] for e in await self.store.history()))
    async def test_no_history_mutation_and_foreign_portfolio_rejected(self):
        await self.svc.tick()
        with sqlite3.connect(self.path) as c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute('delete from auto42_events')
        wrong=Path(self.folder.name)/'other.sqlite3'
        with self.assertRaisesRegex(DemoError,'STORAGE_SCOPE_MISMATCH'):SQLiteStore(wrong)
    async def test_unconfigured_and_render_ephemeral_fail_closed(self):
        self.assertEqual((await configured(self.market).dashboard())['status'],'NOT_OPERATIONAL')
        with patch.dict('os.environ',AURA_AUTO42_SQLITE_PATH=str(self.path),RENDER='true'):
            self.assertEqual((await configured(self.market).dashboard())['reason'],'RENDER_REQUIRES_DURABLE_STORAGE')
    async def test_missed_scheduler_slots_recorded_permanently(self):
        await self.svc.tick();self.now[0]+=900;await self.svc.tick()
        s=(await self.store.load())['state'];self.assertEqual(s['missed_runs'],2)
        self.assertTrue(any(e['kind']=='TICK' and e['payload'].get('missed_slots')==2 for e in await self.store.history()))
    async def test_owner_csrf_scheduler_auth_and_confirmations(self):
        app=FastAPI();app.include_router(router);app.state.auto42=self.svc
        with self.auth():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                self.assertEqual((await c.get('/api/auto42/status')).status_code,401)
                auth=('aura',DUMMY_OWNER);self.assertEqual((await c.get('/api/auto42/status',auth=auth)).status_code,200)
                payload=dict(action='START',request_id='f'*32,expected_revision=1)
                self.assertEqual((await c.post('/api/auto42/control',auth=auth,json=payload)).status_code,403)
                headers={'X-Aura-Paper':'local-only','Origin':'http://evil'}
                self.assertEqual((await c.post('/api/auto42/control',auth=auth,headers=headers,json=payload)).status_code,403)
                headers={'X-Aura-Paper':'local-only'}
                self.assertEqual((await c.post('/api/auto42/control',auth=auth,headers=headers,json=payload)).status_code,409)
                payload['confirmation']='START PAPER';r=await c.post('/api/auto42/control',auth=auth,headers=headers,json=payload)
                self.assertEqual(r.status_code,200);self.assertTrue(r.json()['paper_only'])
                self.assertEqual((await c.post('/api/auto42/tick',auth=auth)).status_code,401)
                r=await c.post('/api/auto42/tick',headers={'X-Aura-Auto42-Token':DUMMY_TOKEN});self.assertEqual(r.status_code,200)
                self.assertNotIn(DUMMY_TOKEN,r.text);self.assertNotIn(DUMMY_OWNER,r.text)
    async def test_stale_dashboard_never_claims_current_equity(self):
        await self.svc.tick();data=await self.svc.dashboard();self.assertEqual(data['status'],'NOT_OPERATIONAL');self.assertIsNone(data['current_equity'])
    async def test_remote_errors_are_sanitized_no_redirect(self):
        for code in (401,403,429,500,307):
            client=SupabaseStore('https://abcdefghijklmnopqrst.supabase.co',DUMMY_KEY,httpx.MockTransport(lambda r:httpx.Response(code,text=DUMMY_KEY)))
            with self.assertRaises(DemoError) as e:await client.load()
            self.assertNotIn(DUMMY_KEY,str(e.exception));await client.close()
    async def test_remote_timeout_network_and_malformed(self):
        for typ in ('timeout','network','malformed'):
            def handle(r):
                if typ=='timeout':raise httpx.ReadTimeout(DUMMY_KEY)
                if typ=='network':raise httpx.ConnectError(DUMMY_KEY)
                return httpx.Response(200,json={'payload':'{}','sha256':'bad','revision':1})
            client=SupabaseStore('https://abcdefghijklmnopqrst.supabase.co',DUMMY_KEY,httpx.MockTransport(handle))
            with self.assertRaises(DemoError) as e:await client.load()
            self.assertNotIn(DUMMY_KEY,str(e.exception));await client.close()


class Boundaries(unittest.TestCase):
    def test_no_exchange_writers_keys_or_old_ledger_imports(self):
        import ast
        for p in Path('app/automated').glob('*.py'):
            s=p.read_text();ast.parse(s)
            for forbidden in ('bybit_demo','testnet.client','BINANCE_TESTNET_API_KEY','BYBIT_DEMO_API_KEY','/api/v3/order','/v5/order','app.paper.engine','app.paper.storage','app.intelligence.replay'):
                self.assertNotIn(forbidden,s)
        sql=Path('scripts/auto42_schema.sql').read_text();self.assertIn('for update',sql.lower());self.assertIn('enable row level security',sql.lower())
        workflow=Path('.github/workflows/aura-auto42.yml').read_text();self.assertIn("vars.AURA_AUTO42_ENABLED == 'true'",workflow)
        self.assertNotIn('SUPABASE_SERVICE',workflow)
