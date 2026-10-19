"""Frozen causal hypotheses; reuse Strategy Lab's three native baselines."""
from decimal import Decimal as D
from app.lab.indicators import ema,rsi,atr,adx
from app.lab.strategies import decisions as native,Decision,PARAMETERS as NATIVE
from app.lab.models import digest

VERSION='AURA_4.3_ACTIVE_PAPER_3'
STEPS={'5m':300,'15m':900,'1h':3600,'4h':14400}
PARAMETERS={**NATIVE,
 'PULLBACK':dict(ema_fast=20,ema_slow=50,adx_min=20,rsi_long_min=50,rsi_short_max=50,sl_atr=2,tp_atr=4),
 'VOLATILITY_BREAKOUT':dict(range_bars=20,compression_bars=20,compression_ratio=.8,volume_multiple=1.2,sl_atr=2,tp_atr=4)}
PROTOCOL=dict(version=VERSION,train_pct=60,validation_pct=20,test_pct=20,starting_balance='10000',
 commission_pct='0.10',slippage_pct='0.05',risk_pct='0.5',daily_loss_pct='2',drawdown_pct='10',max_notional='2000',
 candidates=PARAMETERS,timeframes=list(STEPS),warmup_bars=1000,rolling_anchor='UTC_DAY',
 selection='DEVELOPMENT_AND_VALIDATION_ONLY; frozen before final test; no parameter optimization',
 walk_forward='Three non-overlapping validation/test subsegments; fixed parameters; no final-test reselection',
 source='BITGET_USDT_FUTURES_BTCUSDT_PERPETUAL; public last-trade OHLC; virtual execution; funding not modeled')

def config(name='DONCHIAN',timeframe='15m'):
    if name not in PARAMETERS or timeframe not in STEPS:raise ValueError('Unsupported frozen configuration')
    return dict(strategy=name,timeframe=timeframe,parameters=PARAMETERS[name],version=VERSION,protocol_hash=digest(PROTOCOL))

def signals(bars,name):
    if name in NATIVE:return native(bars,name)
    if name not in PARAMETERS:raise ValueError('Unsupported hypothesis')
    closes=[float(b.close) for b in bars];fast=ema(closes,20);slow=ema(closes,50)
    rs=rsi(closes);at=atr(bars);ax=adx(bars)[0];result=[]
    for i,b in enumerate(bars):
        if i<200 or at[i] is None or at[i]<=0:
            result.append(Decision(reason='WARMUP'));continue
        long=short=False;reason='NO_CONFIRMED_SETUP'
        if name=='PULLBACK':
            long=(fast[i]>slow[i] and ax[i]>=20 and rs[i]>=50 and bars[i-1].low<=D(str(fast[i-1]))
                  and b.close>D(str(fast[i])) and b.close>bars[i-1].high and b.close>b.open)
            short=(fast[i]<slow[i] and ax[i]>=20 and rs[i]<=50 and bars[i-1].high>=D(str(fast[i-1]))
                   and b.close<D(str(fast[i])) and b.close<bars[i-1].low and b.close<b.open)
            if ax[i]<20:reason='ADX_FILTER'
        else:
            prior=bars[i-20:i];base=sum(at[i-20:i])/20;volume=sum(x.volume for x in prior)/20
            compressed=at[i-1]<=base*.8
            long=compressed and volume>0 and b.volume>=volume*D('1.2') and b.close>max(x.high for x in prior)
            short=compressed and volume>0 and b.volume>=volume*D('1.2') and b.close<min(x.low for x in prior)
            if not compressed:reason='NO_VOLATILITY_COMPRESSION'
            elif volume<=0 or b.volume<volume*D('1.2'):reason='VOLUME_FILTER'
        distance=D(str(at[i]))
        result.append(Decision('LONG' if long else 'SHORT' if short else None,distance*2,distance*4,
            False,False,'CLOSED_CANDLE_'+name if long or short else reason))
    return result
