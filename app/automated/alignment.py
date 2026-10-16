"""Read-only evidence for the inputs consumed by Auto42, never a signal source."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import math
import os
from pathlib import Path
import re

SCHEMA='AUTO42_ALIGNMENT_1'
REQUIRED='known_mask == 3 AND direction_15m == direction_1h == direction_4h != 0'
FILES=('app/automated/strategy.py','app/automated/alignment.py',
       'app/intelligence/market_context.py','research/market_intelligence/structure.py',
       'app/lab/indicators.py','app/lab/series.py')
FRAMES=(('15m',900),('1h',3600),('4h',14400))


@lru_cache(maxsize=1)
def code_identity() -> str | None:
    root=Path(__file__).resolve().parents[2]
    try:return hashlib.sha256(b''.join((root/p).read_bytes() for p in FILES)).hexdigest()
    except OSError:return None


def number(value):
    return value if type(value) in (int,float) and math.isfinite(value) else None


def stamp(value):
    return value if type(value) is int and 0<=value<10**12 else None


def sha256(value):
    return value if isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value) else None


def frame(direction,closed_at,step,indicators,segment_start,at):
    closed=stamp(closed_at);expected=at//step*step if at is not None else None
    values={k:number((indicators or {}).get(k)) for k in ('ema20','ema50','adx14','atr14','rsi14','sample_count')}
    return dict(direction=direction if type(direction) is int and direction in (-1,0,1) else None,
        open_at=closed-step if closed is not None else None,closed_at=closed,expected_closed_at=expected,
        age_at_evaluation_seconds=at-closed if at is not None and closed is not None else None,
        current_at_evaluation=closed is not None and closed==expected,
        segment_start=stamp(segment_start),indicators=values)


def capture(snapshot: dict, now: int, decision: dict, *, error: bool=False) -> dict:
    """Copy whitelisted production inputs; consistency audit is not recomputation.

    No OHLCV, private config, account data or outcome data is captured. Validity
    refers ONLY to alignment input consistency, never execution or profitability.
    """
    state=snapshot.get('state') or {};mtf=state.get('mtf') or {}
    at=stamp(snapshot.get('last_closed_at'));frames={}
    frames['15m']=frame(state.get('trend_direction'),state.get('timestamp'),900,
        state.get('trend_indicators'),state.get('segment_start'),at)
    for tf,key,step in (('1h','h1',3600),('4h','h4',14400)):
        other=mtf.get(key) or {}
        inputs=(snapshot.get('alignment_inputs') or {}).get(tf) or {}
        frames[tf]=frame(other.get('direction'),other.get('closed_at'),step,
            inputs.get('trend_indicators'),inputs.get('segment_start'),at)
    directions=[frames[tf]['direction'] for tf,_ in FRAMES]
    mask=mtf.get('known_mask');mask=mask if type(mask) is int and 0<=mask<=3 else None
    flag=mtf.get('alignment');flag=flag if type(flag) is bool else None
    condition=mask==3 and directions[0] in (-1,1) and directions[0]==directions[1]==directions[2]
    freshness=snapshot.get('freshness') or {}
    fresh=(snapshot.get('status')=='OK' and freshness.get('status')=='FRESH'
        and at is not None and at==now//900*900)
    issues=[];complete=True
    for tf,_ in FRAMES:
        row=frames[tf];values=row['indicators'];fast=values['ema20'];slow=values['ema50']
        if fast is None or slow is None or values['sample_count'] is None:
            complete=False
        else:
            if values['sample_count']<250:issues.append(tf+':INSUFFICIENT_WARMUP')
            expected=1 if fast>slow else -1 if fast<slow else 0
            if expected!=row['direction']:issues.append(tf+':EMA_DIRECTION_MISMATCH')
        if not row['current_at_evaluation']:issues.append(tf+':CLOSED_TIMESTAMP_MISMATCH')
    if mask!=3:issues.append('MTF_HISTORY_NOT_KNOWN')
    if flag is None or flag!=condition:issues.append('ALIGNMENT_FLAG_MISMATCH')
    if not fresh:issues.append('DATA_NOT_FRESH_AT_EVALUATION')
    reason=decision.get('reason')
    if reason=='MTF_NOT_ALIGNED' and condition:issues.append('REJECTION_CONDITION_MISMATCH')
    if not error and reason!='MTF_NOT_ALIGNED' and not condition:issues.append('ALIGNMENT_GATE_BYPASSED')
    if error:
        valid=None;verdict='DATA_REJECTED_ALIGNMENT_NOT_EVALUATED'
    elif not complete:
        valid=None;verdict='INSUFFICIENT_DIAGNOSTIC_EVIDENCE'
    else:
        valid=not issues
        verdict=('VALID_ALIGNMENT_PASS' if condition else 'VALID_ALIGNMENT_REJECTION') if valid else 'INCONSISTENT_INPUTS'
    detail='DATA_REJECTED' if error else 'DIRECTIONS_AGREE' if condition else 'FLAT_TREND' if 0 in directions else 'TREND_DISAGREEMENT'
    revision=os.getenv('RENDER_GIT_COMMIT','')
    return dict(schema=SCHEMA,evaluated_at=now,evaluated_closed_at=at,
        strategy_version=decision.get('version'),parameters_hash=decision.get('parameters_hash'),
        code_identity=code_identity(),render_commit=revision if re.fullmatch(r'[0-9a-f]{40}',revision) else None,
        source_sha256=sha256((snapshot.get('history') or {}).get('source_sha256')),
        frames=frames,required_condition=REQUIRED,known_mask=mask,alignment_flag=flag,
        actual_condition=condition,alignment_evaluated=not error,
        strategy_reason=reason,detail=detail,decision_valid=valid,verdict=verdict,
        validation_scope='ALIGNMENT_INPUT_CONSISTENCY_ONLY',issues=issues,
        freshness=dict(fresh_at_evaluation=fresh,fetched_at=number(snapshot.get('fetched_at')),
            analyzed_at=number(snapshot.get('analyzed_at')),delivery_age_seconds=number(freshness.get('delivery_age_seconds'))))


def present(saved: dict | None, now: int) -> dict:
    """Present saved evidence only. Never fetch market data or mutate a ledger."""
    if not isinstance(saved,dict) or saved.get('schema')!=SCHEMA:
        return dict(status='NOT_CAPTURED',snapshot=None,decision_valid=None,
            message='No saved production alignment inputs. Historical reason alone is insufficient.')
    # Only the schema generated here is stored; never return arbitrary state fields.
    allowed=('schema','evaluated_at','evaluated_closed_at','strategy_version','parameters_hash',
        'code_identity','render_commit','source_sha256','frames','required_condition','known_mask',
        'alignment_flag','actual_condition','alignment_evaluated','strategy_reason','detail',
        'decision_valid','verdict','validation_scope','issues','freshness')
    value={k:deepcopy(saved.get(k)) for k in allowed}
    age=now-saved['evaluated_at'] if stamp(saved.get('evaluated_at')) is not None else None
    return dict(status='CAPTURED',snapshot=value,age_seconds=age,
        current_code_matches=code_identity() is not None and saved.get('code_identity')==code_identity(),
        current_data_fresh=bool(age is not None and 0<=age<900 and
            saved.get('evaluated_closed_at')==now//900*900 and
            (saved.get('freshness') or {}).get('fresh_at_evaluation')),
        decision_valid=saved.get('decision_valid'))
