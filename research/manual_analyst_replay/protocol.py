"""Chronological frozen splits and honest calendar-exposure classification."""
from .config import Config,digest


def validate_protocol(p: dict, data_end: int) -> Config:
    if p.get('version')!=1:raise ValueError('PROTOCOL_VERSION')
    for k in ('start','end','frozen_at'):
        if type(p.get(k)) is not int or p[k]<=0:raise ValueError('PROTOCOL_TIME')
    if p['start']%300 or p['end']%300 or not p['start']<p['end']<=data_end or p['end']-p['start']<1500:
        raise ValueError('PROTOCOL_RANGE')
    if p.get('splits')!=[60,20,20] or type(p.get('exposure_registry_complete')) is not bool:
        raise ValueError('FROZEN_SPLITS_REQUIRED')
    previous=p.get('prior_exposure')
    if not isinstance(previous,list) or len(previous)>2000:raise ValueError('EXPOSURE_REGISTRY_REQUIRED')
    for r in previous:
        if not isinstance(r,dict) or type(r.get('start')) is not int or type(r.get('end')) is not int or not 0<r['start']<r['end']:
            raise ValueError('INVALID_EXPOSURE')
    cfg=Config(**p['config']);cfg.validate();return cfg


def splits(p: dict, manifest: dict) -> list[dict]:
    n=(p['end']-p['start'])//300
    a=p['start']+int(n*.6)*300;b=p['start']+int(n*.8)*300
    result=[]
    for name,left,right in [('development',p['start'],a),('validation',a,b),('test',b,p['end'])]:
        overlaps=[r for r in p['prior_exposure'] if max(left,r['start'])<min(right,r['end'])]
        reasons=[]
        if overlaps:reasons.append('PREVIOUSLY_VIEWED_CALENDAR')
        if not p['exposure_registry_complete']:reasons.append('EXPOSURE_REGISTRY_NOT_PROVEN_COMPLETE')
        if p['frozen_at']>left:reasons.append('CONFIG_FROZEN_AFTER_PERIOD_STARTED')
        if manifest['availability_mode']!='OBSERVED':reasons.append('ASSUMED_HISTORICAL_AVAILABILITY')
        if manifest['data_kind']!='REAL_PUBLIC_ARCHIVE':reasons.append('SYNTHETIC_DATA')
        result.append(dict(name=name,start=left,end=right,
            independence='NOT_INDEPENDENT' if reasons else 'PROSPECTIVE_BY_DECLARED_REGISTRY_NOT_EXTERNALLY_ATTESTED',
            reasons=reasons,prior_exposure_count=len(overlaps)))
    return result
