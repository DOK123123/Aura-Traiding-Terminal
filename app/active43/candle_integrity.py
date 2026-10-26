"""Active43-only exact numeric identity; no rounding or shared-ledger migration."""
from decimal import Decimal, InvalidOperation
from app.lab.models import Bar, digest, LabError

FIELDS=('open','high','low','close','volume')


def decimal_text(value: Decimal) -> str:
    if not isinstance(value,Decimal) or not value.is_finite():raise ValueError('INVALID_DECIMAL')
    # normalize() can round to the active Decimal context. Fixed formatting and
    # removing fractional zeroes preserve every significant digit instead.
    if value==0:return '0'
    parts=value.as_tuple()
    if value.adjusted()>30 or parts.exponent < -80 or len(parts.digits)>80:raise ValueError('DECIMAL_LIMIT')
    raw=format(value,'f')
    if len(raw)>80:raise ValueError('DECIMAL_LIMIT')
    return raw.rstrip('0').rstrip('.') if '.' in raw else raw


def canonical_data(bar: Bar) -> dict:
    return dict(time=bar.time,**{key:decimal_text(getattr(bar,key)) for key in FIELDS})


def candle_hash(bar: Bar) -> str:
    return digest(canonical_data(bar))


def verified_anchor(state: dict) -> Bar | None:
    """Only use stored fields whose legacy OR numeric digest proves identity."""
    old=state.get('last_anchor_ohlcv');watermark=state.get('watermark')
    if not isinstance(old,dict) or set(old)!={'time',*FIELDS} or type(watermark) is not int:return None
    try:
        if type(old['time']) is not int or old['time']!=watermark-{'5m':300,'15m':900,'1h':3600,'4h':14400}[state['config']['timeframe']]:return None
        if any(not isinstance(old[k],str) or len(old[k])>80 for k in FIELDS):return None
        bar=Bar(old['time'],*[Decimal(old[k]) for k in FIELDS])
        bar.validate(watermark-old['time'],watermark)
        return bar if state.get('last_bar_hash') in (digest(old),candle_hash(bar)) else None
    except (KeyError,ValueError,InvalidOperation,LabError):return None


def anchor_matches(state: dict, bar: Bar) -> bool:
    stored=state.get('last_bar_hash')
    if stored in (digest(bar.data()),candle_hash(bar)):return True
    old=verified_anchor(state)
    return old is not None and canonical_data(old)==canonical_data(bar)
