"""Frozen baseline, strict BTC candle contract and reproducible JSON serialization."""
from dataclasses import dataclass,asdict
from decimal import Decimal,localcontext,ROUND_HALF_EVEN,ROUND_CEILING,ROUND_DOWN
from functools import wraps
import hashlib
import json
import re

D=Decimal
STEPS={'15m':900,'1h':3600,'4h':14400}
VERSION='STRATEGY_LAB_1.1.0'
SOURCE='Binance · Spot / data-api.binance.vision'
WARMUP_4H=250
MAX_BASE_BARS=12000
MONEY=D('0.00000001')
QTY=D('0.000000000001')


class LabError(Exception):
    def __init__(self,code):self.code=code;super().__init__(code)


def precise(fn):
    @wraps(fn)
    def call(*a,**k):
        with localcontext() as ctx:
            ctx.prec=64
            return fn(*a,**k)
    return call


def number(value,positive=False):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{1,24}(?:\.[0-9]{1,16})?',value):raise LabError('INVALID_DATA')
    n=D(value)
    if not n.is_finite() or n>D('1000000000000000000000000') or (positive and n<=0):raise LabError('INVALID_DATA')
    return n


def money(n,ceil=False):
    with localcontext() as ctx:
        ctx.prec=64
        return n.quantize(MONEY,rounding=ROUND_CEILING if ceil else ROUND_HALF_EVEN)


def quantity(n):return n.quantize(QTY,rounding=ROUND_DOWN)
def text(n):return None if n is None else format(n,'f')
def canonical(data):return json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(data):return hashlib.sha256(canonical(data)).hexdigest()


@dataclass(frozen=True)
class Bar:
    time:int
    open:Decimal
    high:Decimal
    low:Decimal
    close:Decimal
    volume:Decimal

    def validate(self,step,closed_through):
        if type(self.time) is not int or self.time<0 or self.time%step or self.time+step>closed_through:raise LabError('INVALID_TIMESTAMPS')
        for n in (self.open,self.high,self.low,self.close,self.volume):
            if not isinstance(n,D) or not n.is_finite():raise LabError('INVALID_OHLCV')
        if self.low<=0 or max(self.open,self.high,self.close)>D('1000000000000') or self.volume<0:raise LabError('INVALID_OHLCV')
        if self.high<max(self.open,self.close,self.low) or self.low>min(self.open,self.close):raise LabError('INVALID_OHLCV')

    def data(self):return dict(time=self.time,**{k:text(getattr(self,k)) for k in ('open','high','low','close','volume')})
    @classmethod
    def restore(cls,row):return cls(row['time'],*[number(row[k]) for k in ('open','high','low','close','volume')])


@dataclass(frozen=True)
class Baseline:
    starting_balance:str='10000'
    fee_bps:str='10'
    slippage_bps:str='5'
    risk_pct:str='1'
    max_notional:str='2000'
    min_trades:int=20
    sharpe_min_daily_returns:int=30
    development_pct:str='70'

    def validate(self):
        for key in ('starting_balance','fee_bps','slippage_bps','risk_pct','max_notional','development_pct'):number(getattr(self,key))
        if not D('.01')<=D(self.starting_balance)<=D('1000000000') or not 0<=D(self.fee_bps)<=100 or not 0<=D(self.slippage_bps)<=100:raise LabError('INVALID_CONFIG')
        if not 0<D(self.risk_pct)<=5 or not D('.01')<=D(self.max_notional)<=D('1000000000') or not 50<=D(self.development_pct)<=90:raise LabError('INVALID_CONFIG')
        if self.min_trades!=20 or self.sharpe_min_daily_returns!=30:raise LabError('INVALID_CONFIG')
        if any(D(getattr(self,k))!=money(D(getattr(self,k))) for k in ('starting_balance','max_notional')):raise LabError('INVALID_CONFIG')
    def data(self):return asdict(self)


def validate_series(bars,step,end):
    if not bars:raise LabError('INSUFFICIENT_DATA')
    for b in bars:b.validate(step,end)
    for a,b in zip(bars,bars[1:]):
        if b.time<=a.time:raise LabError('DUPLICATE_OR_UNORDERED')
        if b.time-a.time!=step:raise LabError('MISSING_CANDLES')
