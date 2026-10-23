"""Grounded, frozen hypotheses. Literature motivates tests, not profitability."""
from copy import deepcopy
from app.lab.models import digest

SOURCES={
 'JEG1990':dict(authors='Narasimhan Jegadeesh',year=1990,title='Evidence of Predictable Behavior of Security Returns',url='https://doi.org/10.1111/j.1540-6261.1990.tb05110.x',scope='Monthly US equity reversal; not evidence for BTC intraday net returns.'),
 'CONT2014':dict(authors='Rama Cont; Arseniy Kukanov; Sasha Stoikov',year=2014,title='The Price Impact of Order Book Events',url='https://doi.org/10.1093/jjfinec/nbt003',scope='Equity order-book microstructure. OHLCV cannot identify actual liquidity sweeps or stop hunts.'),
 'BROCK1992':dict(authors='William Brock; Josef Lakonishok; Blake LeBaron',year=1992,title='Simple Technical Trading Rules and the Stochastic Properties of Stock Returns',url='https://doi.org/10.1111/j.1540-6261.1992.tb04681.x',scope='Historical Dow trading-range rules; not BTC cost-adjusted validation.'),
 'HAM1989':dict(authors='James D. Hamilton',year=1989,title='A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle',url='https://doi.org/10.2307/1912559',scope='Macroeconomic regime methodology. Our ADX threshold classifier is not a fitted Hamilton model.'),
 'MOP2012':dict(authors='Tobias J. Moskowitz; Yao Hua Ooi; Lasse Heje Pedersen',year=2012,title='Time series momentum',url='https://doi.org/10.1016/j.jfineco.2011.11.003',scope='Traditional futures momentum; no BTC15m profitability claim.'),
 'LIU2021':dict(authors='Yukun Liu; Aleh Tsyvinski',year=2021,title='Risks and Returns of Cryptocurrency',url='https://doi.org/10.1093/rfs/hhaa113',scope='Cryptocurrency return predictability, not proof for this strategy/cost model.')}

HYPOTHESES={
 'MEAN_REVERSION':dict(title='Mean Reversion — existing RSI regime entry',sources=['JEG1990'],rationale='Temporary overshoot may revert in a weak trend; fees can erase the effect.',rules='Reuse Candidate C entry: RSI14 returns above30 LONG/below70 SHORT; ADX14<=20 and abs(EMA20-EMA50)/ATR14<=0.5. Protective SL/TP only; Candidate C strategy-exit flags are intentionally NOT used.',parameters=dict(rsi=14,rsi_low=30,rsi_high=70,adx_max=20,spread_atr_max='0.5',sl_atr=2,tp_atr=4)),
 'LIQUIDITY_SWEEP':dict(title='Liquidity Sweep — OHLCV failed-breakout proxy',sources=['CONT2014'],rationale='A rejected prior-range break may reflect transitory price pressure; candles cannot prove liquidity removal.',rules='Prior20 range excludes current candle. LONG low < prior low -0.1 ATR, close > prior low, bullish body; SHORT mirrored. Relative volume>=1.2 and ADX<25. SL2ATR/TP4ATR.',parameters=dict(window=20,penetration_atr='0.1',relative_volume='1.2',adx_max=25,sl_atr=2,tp_atr=4)),
 'VOLATILITY_BREAKOUT':dict(title='Volatility Breakout — reuse Lab v2 Donchian',sources=['BROCK1992','LIU2021'],rationale='Range expansion with participation may persist; false breaks and execution costs can dominate.',rules='Exact existing Lab v2 DONCHIAN gates: prior20 range +0.1ATR close breakout, directed body, EMA20/50, ADX>=20, relative volume>=1.25; SL2ATR/TP4ATR. No duplicate implementation.',parameters=dict(implementation='app.lab.v2_strategies.decide:DONCHIAN')),
 'REGIME_SWITCHING':dict(title='Market Regime Switching — causal ADX classifier',sources=['HAM1989','MOP2012','JEG1990'],rationale='Continuation and reversal may apply in different states; classification can lag and overfit.',rules='Only last closed1h ADX: <=20 use mean-reversion entry; >=25 use existing Lab v2 TREND_ATR entry on15m; transition no entry. Protective fixed SL/TP, no fitted HMM or future smoothing.',parameters=dict(context='1h',range_adx=20,trend_adx=25,transition='NO_ENTRY'))}

PROTOCOL=dict(version='AURA_AI_RESEARCH_LAB_1',symbol='BTCUSDT',train_pct=60,validation_pct=20,test_pct=20,
 start=1760572800,end_exclusive=1792108800,timeframe='15m',context_timeframes=['1h','4h'],
 sensitivity_scales=['0.9','1','1.1'],sensitivity_scope=['train','validation'],test_scale='1',
 optimization=False,selection='NONE; ALL FROZEN HYPOTHESES REPORTED',min_closed_trades=30,
 candidate_for_paper_enabled=False,test_classification='REUSED_EXPLORATORY_TEST',
 observed_period_start=1577836800,observed_period_end_exclusive=1792108800,
 limitations=['All supplied history was previously examined in main research and/or PR3-5.',
 'No fresh independent test is available. No strategy can be promoted in v1.',
 'SHORT is virtual directional exposure on Binance Spot quotes, not Spot borrowing or futures.',
 'OHLC next-open fills are modeled; funding, borrow, impact, outages and latency are not modeled.',
 'Net equity includes any open-position liquidation mark; PF/WR/expectancy concern closed trades only.',
 'Sample thresholds, parameter sensitivity and a positive backtest do not prove an edge.'])

def registry() -> dict:
    return {k:dict(id=k,status='RESEARCHING',hypothesis_hash=digest(v),**deepcopy(v)) for k,v in HYPOTHESES.items()}
