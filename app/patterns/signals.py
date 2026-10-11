"""Transparent evidence score. Not a calibrated probability of profit."""
import math


def wilson_lower(successes,n):
    if not n: return 0.
    z=1.96; p=successes/n
    return (p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n)


def decide(stats,matches,facts,mtf,config):
    n=len(matches); main=stats[str(config.decision_horizon)]
    similarity=sum(m['similarity'] for m in matches)/n if n else 0
    side='LONG' if (main['up_pct'] or 0)>=(main['down_pct'] or 0) else 'SHORT'
    direction=1 if side=='LONG' else -1
    rate=(main['up_pct'] if side=='LONG' else main['down_pct']) or 0
    sample=min(1,n/(config.minimum_sample*2))
    consistency=sum(direction*(s['median_move_pct'] or 0)>0 and direction*(s['average_move_pct'] or 0)>0 for s in stats.values())/len(stats)
    volatility=1/max(1,facts['volatility_ratio'])
    available=[m for m in mtf if m['trend']!='UNAVAILABLE']
    confirming=[m for m in available if m['trend']==('Bullish' if side=='LONG' else 'Bearish')]
    confirmation=len(confirming)/len(available) if available else .5
    # Absence of MTF evidence is neutral, never invented confirmation.
    confidence=100*sample*(similarity/100)*(rate/100)*(.5+.5*consistency)*volatility*(.75+.25*confirmation)
    successes=main['up'] if side=='LONG' else main['down']
    lower=wilson_lower(successes,n)
    reasons=[]; bullish=[]; bearish=[]; risks=[]
    (bullish if facts['ema20']>facts['ema50'] else bearish).append('EMA20 выше EMA50' if facts['ema20']>facts['ema50'] else 'EMA20 не выше EMA50')
    (bullish if facts['rsi_change']>0 else bearish).append(f"Изменение RSI за 5 свечей: {facts['rsi_change']:+.2f}")
    if n:
        reasons.append(f"Через {config.decision_horizon} свечей: UP {main['up_pct']:.1f}%, DOWN {main['down_pct']:.1f}%, FLAT {main['flat']} из {n}.")
    if n<config.minimum_sample: risks.append(f'LOW SAMPLE SIZE: {n}, минимум {config.minimum_sample}.')
    if rate<config.signal_threshold: risks.append('Доля направленных исходов ниже порога преимущества.')
    if lower<=.5: risks.append('Нижняя граница Wilson 95% не превышает 50%; преимущество не подтверждено.')
    if facts['volatility_ratio']>1.5: risks.append(f"Волатильность повышена в {facts['volatility_ratio']:.2f} раза.")
    if facts['distance_high_atr']<.5: risks.append('Цена ближе 0.5 ATR к локальному high.')
    if facts['distance_low_atr']<.5: risks.append('Цена ближе 0.5 ATR к локальному low.')
    for m in mtf:
        reasons.append(f"{m['timeframe']}: {m['trend']} ({m['bars']} полных свечей того же источника).")
    if not facts['volume_available']: risks.append('Объём отсутствует/непригоден: признак объёма исключён из расстояния.')
    expected=direction*(main['average_move_pct'] or 0)
    if expected<=config.round_trip_cost_bps/100: risks.append('Среднее направленное движение не покрывает заданные расходы.')
    eligible=(n>=config.minimum_sample and rate>=config.signal_threshold and lower>.5
              and confidence>=config.minimum_confidence and expected>config.round_trip_cost_bps/100
              and direction*(main['median_move_pct'] or 0)>0 and consistency>=.5)
    if confidence<config.minimum_confidence: risks.append('Confidence score ниже минимального порога.')
    return dict(signal=side if eligible else 'WAIT',confidence=round(confidence,2),
                confidence_label='Evidence score, not probability',average_similarity=similarity if n else None,
                historical_matches=n,low_sample_size=n<config.minimum_sample,
                directional_rate_pct=rate,wilson_lower_pct=100*lower,
                confidence_components=dict(sample=sample,similarity=similarity/100,directional_rate=rate/100,
                                           consistency=consistency,volatility=volatility,mtf=confirmation),
                explanation=dict(bullish=bullish,bearish=bearish,evidence=reasons,risks=risks))
