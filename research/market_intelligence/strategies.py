"""Six frozen contextual research rules; no broker clients or activation."""
from decimal import Decimal as D
from app.lab.strategies import Decision

FAMILIES=('BREAKOUT_CONTINUATION','FAILED_BREAKOUT_REVERSAL','BREAKOUT_RETEST',
    'TREND_PULLBACK','RANGE_MEAN_REVERSION','VOLATILITY_EXPANSION')

RULES={
 'BREAKOUT_CONTINUATION':'New confirmed close breakout; EMA direction agrees, ADX>=25 and relative volume>=1.5.',
 'FAILED_BREAKOUT_REVERSAL':'Within8 closed bars of breakout, close back through broken level by0.1ATR; choose opposite side.',
 'BREAKOUT_RETEST':'Within8 bars after breakout (not same bar), touch0.25ATR level zone and confirming directional body/close beyond0.1ATR.',
 'TREND_PULLBACK':'ADX>=25, full15m/1h/4h EMA alignment, pullback depth0.5..2ATR and directional candle body.',
 'RANGE_MEAN_REVERSION':'ADX<=20 and prior50 width<=6ATR; range position<=.15 with RSI<=40 LONG or >=.85 and RSI>=60 SHORT.',
 'VOLATILITY_EXPANSION':'ATR/close versus previous64 median>=1.5, volume>=1.5, breakout in EMA direction.'}


def candidates(bar,row):
    if row is None:return {}
    direction='LONG' if row['trend_direction']==1 else 'SHORT' if row['trend_direction']==-1 else None
    result={};broken=row['breakout'];strength=row['trend_strength']
    if broken and broken==direction and strength>=25 and row['volume_confirmed']:result['BREAKOUT_CONTINUATION']=broken
    if row['failed_breakout']:result['FAILED_BREAKOUT_REVERSAL']=row['failed_breakout']
    if row['retest']:result['BREAKOUT_RETEST']=row['retest']
    if strength>=25 and row['mtf']['alignment'] and .5<=row['pullback_depth_atr']<=2 and (bar.close>bar.open if direction=='LONG' else bar.close<bar.open):
        result['TREND_PULLBACK']=direction
    if row['range_detected']:
        if row['range_position']<=.15 and row['rsi']<=40:result['RANGE_MEAN_REVERSION']='LONG'
        elif row['range_position']>=.85 and row['rsi']>=60:result['RANGE_MEAN_REVERSION']='SHORT'
    if row['volatility']=='EXPANSION' and row['volume_confirmed'] and broken and broken==direction:result['VOLATILITY_EXPANSION']=broken
    return result


def invalidation(family,row):
    if row is None:return True,True
    if family=='ALL':return False,False
    if family in ('BREAKOUT_CONTINUATION','BREAKOUT_RETEST','VOLATILITY_EXPANSION'):
        return row['trend_direction']!=1 or row['failed_breakout']=='SHORT',row['trend_direction']!=-1 or row['failed_breakout']=='LONG'
    if family=='FAILED_BREAKOUT_REVERSAL':return row['breakout']=='SHORT',row['breakout']=='LONG'
    if family=='TREND_PULLBACK':return not row['mtf']['alignment'] or row['trend_direction']!=1,not row['mtf']['alignment'] or row['trend_direction']!=-1
    if family=='RANGE_MEAN_REVERSION':return row['range_position']>=.5 or not row['range_detected'],row['range_position']<=.5 or not row['range_detected']
    raise ValueError('Unknown family')


def decision(bar,row,family,side,protect):
    if protect not in ('PCT_2_4','ATR_2_4'):raise ValueError('Unknown protective policy')
    stop=bar.close*D('.02') if protect=='PCT_2_4' else D(str(row['atr']))*2 if row else None
    target=stop*2 if stop is not None else None
    xl,xs=invalidation(family,row);expire=(bar.time+900)%86400==0
    return Decision(side,stop,target,xl or expire,xs or expire,'MARKET_CONTEXT:'+family)
