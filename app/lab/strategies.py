"""Independent fixed research baselines; no activation/optimization path."""
from dataclasses import dataclass
from decimal import Decimal
from .indicators import ema,rsi,atr,adx
from .models import precise

PARAMETERS={
 'DONCHIAN':{'entry_channel':20,'exit_channel':10,'atr_period':14,'sl_atr':2,'tp_atr':4},
 'TREND_ATR':{'ema_fast':50,'ema_slow':200,'atr_period':14,'sl_atr':2,'tp_atr':4},
 'EMA_RSI_ADX':{'ema_fast':20,'ema_slow':50,'rsi_period':14,'adx_period':14,'adx_entry':25,'adx_exit':20,'rsi_long':55,'rsi_short':45,'atr_period':14,'sl_atr':2,'tp_atr':4}}
AURA_INCOMPATIBILITY='Existing Aura replay uses fixed-horizon exits, 100% notional and round-trip bps. It emits no strategy SL/TP. Applying common ATR stops, fee/slippage and risk-sized execution would change its semantics; excluded from shared-engine ranking. Existing Aura strategy/backtest remains unchanged.'


@dataclass(frozen=True)
class Decision:
    direction:str | None=None
    stop_distance:Decimal | None=None
    target_distance:Decimal | None=None
    exit_long:bool=False
    exit_short:bool=False
    reason:str='NO_SIGNAL'


@precise
def decisions(bars,name):
    closes=[float(b.close) for b in bars];at=atr(bars)
    if name=='DONCHIAN':warm=20
    elif name=='TREND_ATR':fast,slow=ema(closes,50),ema(closes,200);warm=199
    elif name=='EMA_RSI_ADX':fast,slow=ema(closes,20),ema(closes,50);rs=rsi(closes);ax,p,m=adx(bars);warm=49
    else:raise ValueError('Unsupported research strategy')
    result=[]
    for i,b in enumerate(bars):
        if i<warm or at[i] is None or at[i]<=0:result.append(Decision(reason='WARMUP_OR_FLAT_ATR'));continue
        long=short=exit_long=exit_short=False
        if name=='DONCHIAN':
            long=b.close>max(v.high for v in bars[i-20:i]);short=b.close<min(v.low for v in bars[i-20:i])
            exit_long=b.close<min(v.low for v in bars[i-10:i]);exit_short=b.close>max(v.high for v in bars[i-10:i])
        elif name=='TREND_ATR':
            long=fast[i]>slow[i] and closes[i]>fast[i];short=fast[i]<slow[i] and closes[i]<fast[i]
            exit_long=fast[i]<=slow[i] or closes[i]<fast[i];exit_short=fast[i]>=slow[i] or closes[i]>fast[i]
        else:
            if ax[i] is None:result.append(Decision(reason='WARMUP'));continue
            long=fast[i]>slow[i] and rs[i]>=55 and ax[i]>=25 and p[i]>m[i]
            short=fast[i]<slow[i] and rs[i]<=45 and ax[i]>=25 and m[i]>p[i]
            exit_long=fast[i]<=slow[i] or rs[i]<50 or ax[i]<20;exit_short=fast[i]>=slow[i] or rs[i]>50 or ax[i]<20
        distance=Decimal(str(at[i]))
        result.append(Decision('LONG' if long else 'SHORT' if short else None,distance*2,distance*4,exit_long,exit_short,
                               'CLOSED_CANDLE_'+name if long or short else 'NO_SIGNAL'))
    return result
