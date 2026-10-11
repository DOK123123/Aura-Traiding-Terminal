from dataclasses import asdict

from .features import build_features, multi_timeframe
from .matching import find_matches
from .outcomes import outcome, statistics
from .signals import decide


def evaluate(candles,timeframe_seconds,context,config,target=None,features=None,include_charts=True):
    target=len(candles)-1 if target is None else target
    if target<context-1 or target<205:
        raise ValueError('Недостаточно истории до выбранной точки для контекста и EMA200.')
    features=features or build_features(candles,config.lookback,context)
    matches=find_matches(features,target,config)
    stats=statistics(candles,matches,config.horizons)
    facts=features.facts[target]
    mtf=multi_timeframe(candles,target,timeframe_seconds)
    result=decide(stats,matches,facts,mtf,config)
    top=[]
    for match in matches[:5]:
        i=match['index']
        item=dict(time=candles[i].time,similarity=match['similarity'],
                  outcomes={str(h):outcome(candles,i,h) for h in config.horizons})
        if include_charts:
            item['candles']=[asdict(c) for c in candles[max(0,i-config.lookback+1):i+max(config.horizons)+1]]
        top.append(item)
    return dict(status='OK',**result,as_of=candles[target].time+timeframe_seconds,
                context=context,context_start=candles[target-context+1].time,
                archive_available_at_decision=target+1,query_time=candles[target].time,
                outcomes=stats,top_matches=top,features=facts,multi_timeframe=mtf,
                config=config.model_dump(),
                method='Causal features; purged non-overlapping matches; horizons in available candles. '
                       'UP/DOWN are observed frequencies; confidence and similarity are uncalibrated scores. '
                       'Wilson bound is descriptive: market dependence and selection remain.')
