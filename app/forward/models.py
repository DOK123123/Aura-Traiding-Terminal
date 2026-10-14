"""Frozen records and causal realized outcomes; independent from trading ledgers."""
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
from app.lab.models import Bar,LabError,canonical,digest,precise
from app.lab.series import higher

VERSION='AURA_FORWARD_4.1'
STEPS={'15m':900,'1h':3600,'4h':14400}
HORIZONS=(4,8,16,32)
POLICY=dict(version=VERSION,creation='Before first future closed candle; UTC exchange boundaries; no backfill',
    scoring='Frozen raw empirical three-class frequencies; zero-probability log loss is infinity, no post-hoc clipping',
    horizons=list(HORIZONS),min_analogs=20,execution='DISABLED',uncertainty='Non-overlap count is not effective independent N')
ROOT=Path(__file__).resolve().parents[2]

class ForwardError(Exception):
    def __init__(self,code):self.code=code;super().__init__(code)


def scheduler_secret_valid(secret,owner='',database_key=''):
    return (32<=len(secret)<=256 and secret.isascii() and secret.isprintable()
            and secret not in (owner,database_key))


def policy_hash():
    return digest(dict(policy=POLICY,software={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
        ('app/forward/models.py','app/forward/stats.py','app/forward/service.py','app/forward/storage.py','app/forward/api.py',
         'scripts/forward_validation_schema.sql','.github/workflows/aura-forward-validation.yml','app/lab/series.py','app/lab/models.py')}))


def record(kind,identifier,payload,created_ms,cohort='',tf='',closed_at=0,ref='',horizon=0):
    text=canonical(payload).decode()
    return dict(id=identifier,kind=kind,created_ms=created_ms,cohort=cohort,tf=tf,closed_at=closed_at,
        ref=ref,horizon=horizon,payload=text,sha256=hashlib.sha256(text.encode()).hexdigest())


def verify(row):
    try:
        if not isinstance(row,dict) or hashlib.sha256(row['payload'].encode()).hexdigest()!=row['sha256']:
            raise ValueError()
        body=json.loads(row['payload'])
        if not isinstance(body,dict):raise ValueError()
        return body
    except (KeyError,TypeError,ValueError,AttributeError):
        raise ForwardError('CORRUPT_JOURNAL') from None


def frame(bars,tf,now):
    if tf not in STEPS:raise ForwardError('INVALID_TIMEFRAME')
    try:
        for b in bars:b.validate(900,int(now))
    except LabError:raise ForwardError('INVALID_MARKET_DATA') from None
    if any(b.time<=a.time for a,b in zip(bars,bars[1:])):raise ForwardError('DUPLICATE_OR_UNORDERED')
    return list(bars) if tf=='15m' else higher(bars,STEPS[tf])


def probabilities(values):
    p=[values.get('negative_frequency'),values.get('zero_frequency'),values.get('positive_frequency')]
    if any(type(v) not in (int,float) or not 0<=v<=1 for v in p) or abs(sum(p)-1)>1e-9:
        raise ForwardError('INVALID_PROBABILITIES')
    return p


@precise
def realized(pred,bars,horizon,now_ms,*,frame_cache=None):
    if type(horizon) is not int or horizon not in HORIZONS:raise ForwardError('INVALID_HORIZON')
    step=STEPS[pred['timeframe']];at=pred['closed_at'];target=at+horizon*step
    if horizon not in HORIZONS or now_ms<target*1000:return None
    fs=frame_cache[pred['timeframe']] if frame_cache is not None else frame(bars,pred['timeframe'],now_ms//1000)
    mapping={b.time:b for b in fs}
    if not fs or fs[-1].time+step<target:return None  # delayed feed, not a fabricated failure
    base=mapping.get(at-step)
    future=[mapping.get(at+i*step) for i in range(horizon)]
    quality='COMPLETE'
    if base is None or any(b is None for b in future):quality='MISSING_CANDLES'
    elif str(base.close)!=pred['closed_price'] and base.close!=D(pred['closed_price']):quality='SOURCE_CORRECTION'
    payload=dict(prediction_id=pred['id'],horizon=horizon,target_closed_at=target,evaluated_at_ms=now_ms,
        actual_price=None,return_pct=None,direction=None,mfe_pct=None,mae_pct=None,quality=quality,
        exchange='Binance',market_type='SPOT',symbol='BTCUSDT',timeframe=pred['timeframe'])
    if quality=='COMPLETE':
        price=D(pred['closed_price']);end=future[-1].close
        ret=(end/price-1)*100
        payload.update(actual_price=str(end),return_pct=str(ret),direction=1 if ret>0 else -1 if ret<0 else 0,
            mfe_pct=str(max(D(0),max(b.high for b in future)/price-1)*100),
            mae_pct=str(min(D(0),min(b.low for b in future)/price-1)*100),
            source_window_sha256=digest([base.data()]+[b.data() for b in future]))
        actual=float(ret);forecast=(pred.get('forecasts') or {}).get(str(horizon))
        payload['prediction_error_pct']=actual-forecast['mean_return_pct'] if forecast else None
        payload['baseline_errors_pct']={k:actual-v['mean_return_pct'] if v.get('mean_return_pct') is not None else None for k,v in (pred.get('baselines') or {}).get(str(horizon),{}).items()}
    payload['fingerprint']=digest({k:v for k,v in payload.items() if k!='evaluated_at_ms'})
    return payload
