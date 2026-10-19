"""Frozen experimental confirmed-structure retest strategy; no analog edge claim."""
from decimal import Decimal as D
import math
from app.lab.models import digest
from app.intelligence.market_context import SOURCE
from research.market_intelligence.structure import VERSION as CONTEXT_VERSION
from .engine import VERSION,DemoError,STEP,validate_bars

PARAMETERS=dict(atr_stop_multiple='1.5',reward_multiple='2',minimum_adx=25,
    retest_lookback=8,volatility_min='0.65',volatility_max='2.0',
    context_version=CONTEXT_VERSION,confirmation='CONFIRMED_BOS_OR_CHOCH_THEN_RETEST',
    liquidity='NO_OPPOSING_OR_AMBIGUOUS_SWEEP')


def strategy(snapshot,bars,now):
    """Attach evidence from the very same evaluation; never re-run analysis."""
    from .alignment import capture
    try:
        result=_evaluate(snapshot,bars,now)
    except DemoError as exc:
        exc.alignment_snapshot=capture(snapshot,now,dict(reason=exc.code),error=True)
        raise
    return dict(result,timeframe_alignment=capture(snapshot,now,result))


def _evaluate(snapshot,bars,now):
    result=dict(direction=None,reason='NO_CONFIRMED_SETUP',version=VERSION,parameters_hash=digest(PARAMETERS),
        classification='EXPERIMENTAL / NO_EDGE_FOUND',source=SOURCE)
    if snapshot.get('status')!='OK' or snapshot.get('freshness',{}).get('status')!='FRESH':raise DemoError('STALE_DATA')
    validate_bars(bars,now)
    at=snapshot.get('last_closed_at');state=snapshot.get('state')
    if (snapshot.get('source')!=SOURCE or snapshot.get('symbol')!='BTCUSDT' or snapshot.get('timeframe')!='15m' or
        type(at) is not int or at!=now//STEP*STEP or not state or state.get('timestamp')!=at or
        state.get('version')!=CONTEXT_VERSION or state.get('symbol')!='BTCUSDT' or state.get('timeframe')!='15m' or
        not bars or bars[-1].time+STEP!=at or (snapshot.get('history') or {}).get('source_sha256')!=digest([b.data() for b in bars])):raise DemoError('SNAPSHOT_MISMATCH')
    if len(bars)<250:raise DemoError('INSUFFICIENT_HISTORY')

    if any(b.time-a.time!=STEP for a,b in zip(bars[-250:],bars[-249:])):raise DemoError('MISSING_CANDLES')
    mtf=state.get('mtf') or {}
    for tf,step in (('h1',3600),('h4',14400)):
        v=mtf.get(tf)
        if not v or type(v.get('closed_at')) is not int or v['closed_at']>at or at-v['closed_at']>=step or v['closed_at']%step:raise DemoError('MTF_UNAVAILABLE')
    if mtf.get('known_mask')!=3 or not mtf.get('alignment'):
        return dict(result,reason='MTF_NOT_ALIGNED')
    side=state.get('retest');trend=state.get('trend_direction')
    if side not in ('LONG','SHORT'):return result
    if trend!=(1 if side=='LONG' else -1) or any(mtf[k].get('direction')!=trend for k in ('h1','h4')):
        return dict(result,reason='TREND_NOT_ALIGNED')
    strength=state.get('trend_strength')
    if type(strength) not in (int,float) or not math.isfinite(strength):raise DemoError('INVALID_ANALYSIS')
    if strength<25:return dict(result,reason='TREND_TOO_WEAK')
    if state.get('regime')!=('TREND_UP' if side=='LONG' else 'TREND_DOWN'):return dict(result,reason='REGIME_FILTER')
    if state.get('liquidity_sweep') in ('AMBIGUOUS','SHORT' if side=='LONG' else 'LONG'):
        return dict(result,reason='OPPOSING_LIQUIDITY')
    events=snapshot.get('structure_events') or []
    matches=[]
    origin=state.get('retest_origin') or {}
    origin_at=origin.get('breakout_closed_at')
    if (origin.get('direction')!=side or type(origin_at) is not int
            or not at-8*STEP<=origin_at<at or origin.get('level')!=state.get('breakout_level')):
        return dict(result,reason='NO_CONFIRMED_STRUCTURE_BREAK')
    # Require a confirmed BOS/CHoCH and its directed breakout at the SAME timestamp.
    for ev in events:
        t=ev.get('confirmed_at')
        if type(t) is int and t==origin_at and ev.get('type')=='structure_event' and ev.get('value') in ('BOS','CHoCH'):
            if any(e.get('type')=='breakout' and e.get('value')==side and e.get('confirmed_at')==t for e in events):matches.append(ev)
    if not matches:return dict(result,reason='NO_CONFIRMED_STRUCTURE_BREAK')
    try:
        atr=D(str(state['atr']));vol=D(str(state['volatility_ratio']));support=D(state['support']);resistance=D(state['resistance']);level=D(state['breakout_level'])
    except (KeyError,TypeError,ValueError,ArithmeticError):raise DemoError('INVALID_ANALYSIS') from None
    if any(not n.is_finite() or n<=0 for n in (atr,vol,support,resistance,level)):raise DemoError('INVALID_ANALYSIS')
    if not D('.65')<=vol<=D('2'):return dict(result,reason='VOLATILITY_FILTER')
    entry=bars[-1].close;long=side=='LONG'
    # Protective level uses observed retest wick and confirmed breakout, plus ATR buffer.
    stop=min(bars[-1].low,level)-atr*D('1.5') if long else max(bars[-1].high,level)+atr*D('1.5')
    distance=abs(entry-stop);target=entry+(1 if long else -1)*distance*2
    if min(stop,target)<=0 or distance<=0:return dict(result,reason='INVALID_STOPS')
    # Nearest opposing level must not block the intended target.
    if (resistance>entry and resistance<target if long else support<entry and support>target):return dict(result,reason='OPPOSING_LEVEL_TOO_CLOSE')
    return dict(result,direction=side,reason='CONFIRMED_STRUCTURE_RETEST',stop_loss=str(stop),take_profit=str(target),
        context=dict(regime=state['regime'],structure=matches[-1],atr=str(atr),liquidity=state.get('liquidity_sweep'),
            support=str(support),resistance=str(resistance),mtf=mtf),signal_at=at)
