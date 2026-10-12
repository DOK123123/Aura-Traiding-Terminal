"""Strict decimal settings and validated closed-candle inputs for paper fills."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN, ROUND_HALF_EVEN, localcontext
import os
import re

STEPS = {'1m': 60, '5m': 300, '15m': 900, '1h': 3600}
MONEY_TICK = Decimal('0.00000001')
QUANTITY_TICK = Decimal('0.000000000001')
REAL_MONEY_EXECUTION = False
AUTOMATIC_SIGNAL_EXECUTION = False


class PaperError(Exception):
    """Fixed public categories; never exceptions, filesystem details or credentials."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def decimal(value: str, *, positive: bool = False, signed: bool = False) -> Decimal:
    pattern = r'-?[0-9]{1,24}(?:\.[0-9]{1,16})?' if signed else r'[0-9]{1,24}(?:\.[0-9]{1,16})?'
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise PaperError('INVALID_DATA')
    result = Decimal(value)
    if not result.is_finite() or abs(result) > Decimal('1000000000000000000') or (positive and result <= 0):
        raise PaperError('INVALID_DATA')
    return result


def money(value: Decimal, *, ceiling: bool = False) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 64
        return value.quantize(MONEY_TICK, rounding=ROUND_CEILING if ceiling else ROUND_HALF_EVEN)


def quantity(value: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 64
        return value.quantize(QUANTITY_TICK, rounding=ROUND_DOWN)


def text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, 'f')


@dataclass(frozen=True)
class Settings:
    starting_balance: Decimal = Decimal('10000')
    commission_pct: Decimal = Decimal('0.10')
    risk_per_trade_pct: Decimal = Decimal('1')
    maximum_position_size_usdt: Decimal = Decimal('2000')
    maximum_simultaneous_positions: int = 1
    stop_loss_pct: Decimal = Decimal('2')
    take_profit_pct: Decimal = Decimal('4')

    @classmethod
    def from_dict(cls, values: dict) -> 'Settings':
        names = set(cls.__dataclass_fields__)
        if not isinstance(values, dict) or set(values) != names:
            raise PaperError('INVALID_SETTINGS')
        try:
            result = cls(**{k:values[k] if k == 'maximum_simultaneous_positions' else decimal(values[k]) for k in names})
            result.validate()
            return result
        except (PaperError, TypeError, ValueError):
            raise PaperError('INVALID_SETTINGS') from None

    @classmethod
    def from_env(cls) -> 'Settings':
        values = cls().to_dict()
        for name in values:
            raw = os.getenv('PAPER_'+name.upper())
            if raw is not None:
                if name == 'maximum_simultaneous_positions':
                    if not re.fullmatch(r'[0-9]{1,2}', raw):
                        raise PaperError('INVALID_SETTINGS')
                    raw = int(raw)
                values[name] = raw
        return cls.from_dict(values)

    def validate(self) -> None:
        if any(not isinstance(v, Decimal) or not v.is_finite() for k,v in self.__dict__.items() if k != 'maximum_simultaneous_positions'):
            raise PaperError('INVALID_SETTINGS')
        if not Decimal('0.01') <= self.starting_balance <= Decimal('1000000000000'):
            raise PaperError('INVALID_SETTINGS')
        if not 0 <= self.commission_pct <= 10 or not 0 < self.risk_per_trade_pct <= 100:
            raise PaperError('INVALID_SETTINGS')
        if not Decimal('0.01') <= self.maximum_position_size_usdt <= Decimal('1000000000000'):
            raise PaperError('INVALID_SETTINGS')
        if type(self.maximum_simultaneous_positions) is not int or not 1 <= self.maximum_simultaneous_positions <= 20:
            raise PaperError('INVALID_SETTINGS')
        if not 0 < self.stop_loss_pct < 100 or not 0 < self.take_profit_pct < 100:
            raise PaperError('INVALID_SETTINGS')
        if any(value != money(value) for value in (self.starting_balance, self.maximum_position_size_usdt)):
            raise PaperError('INVALID_SETTINGS')

    def to_dict(self) -> dict:
        return {k:v if type(v) is int else text(v) for k,v in self.__dict__.items()}


@dataclass(frozen=True)
class Bar:
    time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None

    def validate(self, step: int, now_ms: int) -> None:
        if type(self.time) is not int or self.time < 0 or self.time % step or (self.time+step)*1000 > now_ms:
            raise PaperError('INVALID_MARKET_DATA')
        for value in (self.open, self.high, self.low, self.close):
            if not isinstance(value, Decimal) or not value.is_finite() or not 0 < value <= Decimal('1000000000000'):
                raise PaperError('INVALID_MARKET_DATA')
        if self.volume is not None and (not isinstance(self.volume, Decimal) or not self.volume.is_finite() or self.volume < 0):
            raise PaperError('INVALID_MARKET_DATA')
        if self.high < max(self.open, self.low, self.close) or self.low > min(self.open, self.close):
            raise PaperError('INVALID_MARKET_DATA')


@dataclass(frozen=True)
class Window:
    symbol: str
    timeframe: str
    source: str
    observed_at: int
    bars: tuple[Bar, ...]

    def validate(self, now_ms: int) -> None:
        if self.symbol != 'BTCUSDT' or self.timeframe not in STEPS or not isinstance(self.source, str) or not 1 <= len(self.source) <= 120:
            raise PaperError('INVALID_MARKET_DATA')
        if any(ord(c) < 32 for c in self.source) or not self.bars or len(self.bars) > 500:
            raise PaperError('INVALID_MARKET_DATA')
        if type(self.observed_at) is not int or self.observed_at > now_ms+1000 or now_ms-self.observed_at > 30000:
            raise PaperError('STALE_DATA')
        step = STEPS[self.timeframe]
        for bar in self.bars:
            if not isinstance(bar, Bar):
                raise PaperError('INVALID_MARKET_DATA')
            bar.validate(step, now_ms)
        if any(b.time-a.time != step for a,b in zip(self.bars,self.bars[1:])):
            raise PaperError('MARKET_GAP')
        if now_ms-(self.bars[-1].time+step)*1000 > 2*step*1000:
            raise PaperError('STALE_DATA')

    def quote(self) -> dict:
        bar = self.bars[-1]
        return dict(symbol=self.symbol, timeframe=self.timeframe, source=self.source, price=text(bar.close),
                    candle_time=bar.time, price_time=(bar.time+STEPS[self.timeframe])*1000,
                    observed_at=self.observed_at, fill_model='VERIFIED_CLOSED_CANDLE', paper=True,
                    real_money_execution='DISABLED', automatic_signal_execution=False)
