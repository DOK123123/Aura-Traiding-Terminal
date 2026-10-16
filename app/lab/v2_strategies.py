"""Three frozen research families, causal LONG/SHORT on 15m/1h/4h."""
from decimal import Decimal as D
import math
from .indicators import ema,rsi,atr,adx
from .series import higher
from .models import SOURCE,precise

FAMILIES=('DONCHIAN','TREND_ATR','EMA_RSI_ADX')
STEPS={'15m':900,'1h':3600,'4h':14400}

def prepare(bars,step):
    frame=bars if step==900 else higher(bars,step);close=[float(b.close) for b in frame]
    ax,di_plus,di_minus=adx(frame)
    return dict(bars=frame,step=step,ema20=ema(close,20),ema50=ema(close,50),ema200=ema(close,200),
        rsi=rsi(close),atr=atr(frame),adx=ax,di_plus=di_plus,di_minus=di_minus)

def wait(reason,gates=None):return dict(direction=None,reason=reason,gates=gates or {})

@precise
def decide(data,index,family,*,closed_at):
    if family not in FAMILIES:raise ValueError('UNKNOWN_FAMILY')
    bs=data['bars'];step=data['step']
    if type(index) is not int or index<249 or index>=len(bs):return wait('WARMUP_UNAVAILABLE')
    if bs[index].time+step!=closed_at:return wait('NOT_CLOSED_OR_MISALIGNED')
    if any(b.time-a.time!=step for a,b in zip(bs[index-249:index],bs[index-248:index+1])):return wait('MISSING_CANDLES')
    values=[data[k][index] for k in ('ema20','ema50','ema200','rsi','atr','adx','di_plus','di_minus')]
    if any(type(x) not in (float,int) or not math.isfinite(x) for x in values) or data['atr'][index]<=0:return wait('INDICATORS_UNAVAILABLE')
    b=bs[index];prev=bs[index-1];av=D(str(data['atr'][index]));fast=D(str(data['ema20'][index]));slow=D(str(data['ema50'][index]));long_ema=D(str(data['ema200'][index]))
    ax=data['adx'][index];rs=data['rsi'][index];prior_rs=data['rsi'][index-1];vsum=sum((x.volume for x in bs[index-20:index]),D(0))
    if vsum<=0:return wait('VOLUME_UNAVAILABLE')
    volume=b.volume/(vsum/20)
    if b.high-b.low>av*3:return wait('SHOCK_CANDLE')
    diagnostics={};selected=None;plan_reason=None
    for side,sign in (('LONG',1),('SHORT',-1)):
        if family=='DONCHIAN':
            prior=bs[index-20:index];upper=max(x.high for x in prior);lower=min(x.low for x in prior)
            crossing=(b.close>upper+av*D('.1') and prev.close<=upper) if sign==1 else (b.close<lower-av*D('.1') and prev.close>=lower)
            gates=dict(range_break=crossing,directed_body=sign*(b.close-b.open)>0,ema=sign*(fast-slow)>0,adx=ax>=20,volume=volume>=D('1.25'))
            multiple=2
        elif family=='TREND_ATR':
            cross=(b.close>fast and prev.close<=D(str(data['ema20'][index-1]))) if sign==1 else (b.close<fast and prev.close>=D(str(data['ema20'][index-1])))
            slope=sign*(slow-D(str(data['ema50'][index-1])))>0
            gates=dict(ema_trend=sign*(slow-long_ema)>0,ema_slope=slope,pullback_resume=cross,
                directed_body=sign*(b.close-b.open)>0,adx=ax>=20,rsi=50<=rs<=75 if sign==1 else 25<=rs<=50,volume=volume>=D('.8'))
            multiple=3
        else:
            gates=dict(ema=sign*(fast-slow)>0,price=sign*(b.close-fast)>0,
                rsi_cross=prior_rs<55<=rs if sign==1 else prior_rs>45>=rs,adx=ax>=20,
                directional_index=data['di_plus'][index]>data['di_minus'][index] if sign==1 else data['di_minus'][index]>data['di_plus'][index],volume=volume>=D('.8'))
            multiple=2
        diagnostics[side]=gates
        if not all(gates.values()):continue
        stop=b.close-sign*av*multiple;target=b.close+sign*av*multiple*2
        if min(stop,target)<=0:plan_reason='INVALID_STOPS';continue
        entry=b.close*(1+sign*D('.0005'));sf=stop*(1-sign*D('.0005'));tf=target*(1-sign*D('.0005'))
        risk=sign*(entry-sf)+D('.001')*(entry+sf);reward=sign*(tf-entry)-D('.001')*(entry+tf)
        if risk<=0 or reward/risk<D('1.2'):plan_reason='COST_ADJUSTED_RR_TOO_LOW';continue
        selected=dict(direction=side,reason='LABV2:'+family,source=SOURCE,signal_at=closed_at,stop_loss=str(stop),take_profit=str(target),
            original_signal_at=closed_at,strategy_timeframe={900:'15m',3600:'1h',14400:'4h'}[step],
            context=dict(atr=str(av),adx=ax,rsi=rs,ema20=str(fast),ema50=str(slow),ema200=str(long_ema),relative_volume=str(volume),expected_net_rr=str(reward/risk)))
    return dict(selected or wait(plan_reason or family+'_FILTERS_REJECTED'),gates=diagnostics)
