"""Frozen experiment and execution assumptions; no trading configuration reads."""
from dataclasses import asdict, dataclass
from decimal import Decimal as D
import hashlib
import json


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def decimal(value: str, *, zero: bool = False) -> D:
    import re
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,12}(?:\.\d{1,12})?', value):
        raise ValueError('INVALID_DECIMAL')
    n = D(value)
    if not n.is_finite() or n < 0 or not zero and n == 0:
        raise ValueError('INVALID_DECIMAL')
    return n


@dataclass(frozen=True)
class Config:
    starting_balance: str = '10000'
    risk_pct: str = '0.5'
    max_notional: str = '2000'
    daily_loss_pct: str = '2'
    drawdown_pct: str = '10'
    fee_bps: str = '10'
    slippage_bps: str = '5'
    spread_bps: str = '2'  # Whole spread; adverse half on each side.
    tick: str = '0.1'
    lot: str = '0.0001'
    min_quantity: str = '0.0001'
    min_notional: str = '5'
    latency_seconds: int = 5
    window_bars: int = 200
    max_rows: int = 500000
    deadline_seconds: int = 900
    min_trades: int = 20
    sharpe_min_daily_returns: int = 30
    strategy: str = 'AURA_MANUAL_ANALYST_1_UNCHANGED'

    def validate(self) -> None:
        for k in ('starting_balance','risk_pct','max_notional','daily_loss_pct','drawdown_pct',
                  'tick','lot','min_quantity','min_notional'):
            decimal(getattr(self,k))
        if self.starting_balance != '10000' or not D(self.risk_pct) <= D('.5') or not D(self.max_notional) <= 2000:
            raise ValueError('RISK_CAP')
        if not D(self.daily_loss_pct) <= 2 or not D(self.drawdown_pct) <= 10:
            raise ValueError('LOSS_CAP')
        for k in ('fee_bps','slippage_bps','spread_bps'):
            if decimal(getattr(self,k),zero=True)>100:
                raise ValueError('COST_LIMIT')
        for k,lo,hi in [('latency_seconds',1,30),('max_rows',100,2000000),('deadline_seconds',1,1800)]:
            if type(getattr(self,k)) is not int or not lo <= getattr(self,k) <= hi:
                raise ValueError('RESOURCE_LIMIT')
        if any(type(getattr(self,k)) is not int for k in ('window_bars','min_trades','sharpe_min_daily_returns')):raise ValueError('FROZEN_STRATEGY')
        if self.window_bars != 200 or self.min_trades != 20 or self.sharpe_min_daily_returns != 30 or self.strategy != 'AURA_MANUAL_ANALYST_1_UNCHANGED':
            raise ValueError('FROZEN_STRATEGY')

    def data(self) -> dict:
        self.validate()
        return asdict(self)

    @property
    def hash(self) -> str:
        return digest(self.data())
