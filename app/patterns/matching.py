"""Select on historical features alone, purge overlaps before reading outcomes."""
import numpy as np


def find_matches(features, target, config):
    # A candidate's entire forward outcome must precede the query pattern.
    end = target-config.lookback-max(config.horizons)
    start = features.valid_from
    if end < start:
        return []
    query = features.vectors[target]
    candidates = features.vectors[start:end+1]
    mask = np.isfinite(candidates)&np.isfinite(query)
    difference = np.where(mask,candidates-query,0)**2
    # Sequence and context each receive half the weight, regardless of lookback.
    distances=[]
    for a,b in ((0,21),(21,candidates.shape[1])):
        distances.append(np.sum(difference[:,a:b],axis=1)/np.maximum(1,np.sum(mask[:,a:b],axis=1)))
    distance=np.sqrt((distances[0]+distances[1])/2)
    scores=100*np.exp(-3*distance)
    order=np.argsort(-scores,kind='stable')
    selected=[]
    separation=config.lookback+max(config.horizons)
    for offset in order:
        index=start+int(offset)
        score=float(scores[offset])
        if score<config.minimum_similarity:
            break
        if any(abs(index-m['index'])<separation for m in selected):
            continue
        selected.append(dict(index=index,similarity=score))
        if len(selected)>=config.max_matches:
            break
    return selected
