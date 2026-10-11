"""Observed close returns and OHLC excursions, not estimated probabilities."""
from statistics import mean, median


def outcome(candles, index, horizon):
    entry=candles[index].close
    future=candles[index+1:index+horizon+1]
    if len(future)!=horizon:
        return None
    return dict(move_pct=(future[-1].close/entry-1)*100,
                mfe_pct=max(0,(max(c.high for c in future)/entry-1)*100),
                mae_pct=min(0,(min(c.low for c in future)/entry-1)*100))


def statistics(candles,matches,horizons):
    result={}
    for horizon in horizons:
        rows=[outcome(candles,m['index'],horizon) for m in matches]
        values=[r['move_pct'] for r in rows]
        n=len(rows)
        up=sum(v>0 for v in values); down=sum(v<0 for v in values)
        result[str(horizon)] = dict(count=n,up=up,down=down,flat=n-up-down,
            up_pct=100*up/n if n else None,down_pct=100*down/n if n else None,
            average_move_pct=mean(values) if n else None,median_move_pct=median(values) if n else None,
            max_positive_pct=max([0]+values) if n else None,max_negative_pct=min([0]+values) if n else None,
            mfe_pct=mean(r['mfe_pct'] for r in rows) if n else None,
            mae_pct=mean(r['mae_pct'] for r in rows) if n else None)
    return result
