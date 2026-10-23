"""Offline projection of EXACT production prefix states; no live monkeypatch."""
from bisect import bisect_left
from copy import deepcopy
from app.lab.models import digest
from app.intelligence.market_context import SOURCE

def snapshot(cache,window,at):
    state=deepcopy(cache.states[900][len(window)-1]);inputs={};mask=0;directions=[]
    for j,(step,key,tf) in enumerate(((3600,'h1','1h'),(14400,'h4','4h'))):
        index=bisect_left([b.time for b in cache.frames[step]],at//step*step)-1
        other=cache.states[step][index] if index>=0 else None
        if other and other['segment_start']>=window[0].time and at-other['timestamp']<step:
            mask|=1<<j;state['mtf'][key]=dict(direction=other['trend_direction'],closed_at=other['timestamp'])
            inputs[tf]=dict(trend_indicators=deepcopy(other['trend_indicators']),segment_start=other['segment_start'])
        directions.append(other['trend_direction'] if mask&(1<<j) else 0)
    state['mtf']['known_mask']=mask;state['mtf']['alignment']=mask==3 and directions[0]==directions[1]==state['trend_direction']!=0
    state['vector'][-3:]=directions+[mask];events=[]
    for row in cache.states[900][max(0,len(window)-32):len(window)]:
        if not row:continue
        for name in ('breakout','failed_breakout','retest','structure_event','liquidity_sweep'):
            if row[name]:events.append(dict(type=name,value=row[name],confirmed_at=row['timestamp']))
        for pivot in row['confirmed_pivots']:events.append(dict(type='swing',**pivot))
    return dict(status='OK',freshness=dict(status='FRESH'),symbol='BTCUSDT',timeframe='15m',source=SOURCE,
        last_closed_at=at,state=state,alignment_inputs=inputs,history=dict(source_sha256=digest([b.data() for b in window])),
        structure_events=events[-32:],fetched_at=at+30,analyzed_at=at+30)
