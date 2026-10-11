"""Walk-forward replay: predict at close, execute next open, fixed horizon."""
from statistics import mean

from .engine import evaluate
from .features import build_features
from .outcomes import outcome


def replay(candles,step,context,config,start_at=None,end_at=None,max_points=50):
    features=build_features(candles,config.lookback,context)
    horizon=config.decision_horizon
    start=max(features.valid_from+config.lookback+max(config.horizons)+config.minimum_sample*(config.lookback+max(config.horizons)),context-1)
    if start_at is not None:
        candidates=[i for i,c in enumerate(candles) if c.time+step>=start_at and i>=features.valid_from]
        if not candidates: raise ValueError('Начало backtest вне доступной истории.')
        start=candidates[0]
    stop=len(candles)-horizon-1
    if end_at is not None:
        stop=min(stop,max((i for i,c in enumerate(candles) if c.time+step<=end_at),default=-1))
    if stop<start: raise ValueError('Недостаточно истории/будущих свечей для выбранного backtest.')
    points=list(range(start,stop+1,horizon))[:max_points]
    results=[]; trades=[]; equity=peak=1.; max_drawdown=0.
    for i in points:
        prediction=evaluate(candles,step,context,config,i,features,False)
        side=prediction['signal']
        actual=outcome(candles,i,horizon)
        net=None
        if side!='WAIT':
            entry=candles[i+1].open
            gross=(candles[i+horizon].close/entry-1)*100*(1 if side=='LONG' else -1)
            net=gross-config.round_trip_cost_bps/100
            trades.append(dict(side=side,return_pct=net))
            equity=max(0,equity*(1+net/100)); peak=max(peak,equity)
            max_drawdown=max(max_drawdown,100*(peak-equity)/peak)
        results.append(dict(time=candles[i].time,as_of=prediction['as_of'],signal=side,
                            confidence=prediction['confidence'],historical_matches=prediction['historical_matches'],
                            actual_close_move_pct=actual['move_pct'],net_return_pct=net,
                            entry_time=candles[i+1].time if side!='WAIT' else None,
                            exit_time=candles[i+horizon].time+step if side!='WAIT' else None))
    wins=sum(t['return_pct']>0 for t in trades); losses=sum(t['return_pct']<0 for t in trades)
    profit=sum(max(0,t['return_pct']) for t in trades); loss=-sum(min(0,t['return_pct']) for t in trades)
    def accuracy(side):
        subset=[t for t in trades if t['side']==side]
        return 100*sum(t['return_pct']>0 for t in subset)/len(subset) if subset else None
    return dict(status='OK',mode='BACKTEST',config=config.model_dump(),points=results,
                summary=dict(total_decisions=len(points),total_signals=len(trades),wins=wins,losses=losses,
                    flat_trades=len(trades)-wins-losses,win_rate=100*wins/len(trades) if trades else None,
                    average_return_pct=mean(t['return_pct'] for t in trades) if trades else None,
                    profit_factor=profit/loss if loss else None,profit_factor_note='undefined without losses' if not loss else '',
                    max_drawdown_pct=max_drawdown,long_accuracy=accuracy('LONG'),short_accuracy=accuracy('SHORT'),
                    wait_frequency=100*(len(points)-len(trades))/len(points),equity_return_pct=(equity-1)*100),
                truncated=len(range(start,stop+1,horizon))>max_points,
                method='Fixed horizon, next-open entry, close exit; non-overlapping decisions/trades. '
                       '100% notional, no leverage. Net of configured round-trip bps; no spread/slippage model. '
                       'WAIT is excluded from trade win rate. No fitting or parameter optimization.')
