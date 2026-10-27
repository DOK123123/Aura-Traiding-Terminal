"""Isolated, offline manual-paper accounting prototype. No exchange or database I/O.

The API supplies server-verified Bitget bid/ask prices. No exchange execution.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

D = Decimal


def number(value):
    try:
        result = D(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("INVALID_NUMBER") from None
    if (not result.is_finite() or result <= 0 or not -12 <= result.adjusted() <= 12
            or len(result.as_tuple().digits) > 28):
        raise ValueError("INVALID_NUMBER")
    return result


@dataclass(frozen=True)
class Position:
    side: str
    quantity: Decimal
    entry: Decimal
    stop: Decimal
    target: Decimal
    entry_fee: Decimal
    entry_candle_time: int | None = None
    id: str | None = None


class ManualPaper:
    """Virtual-only one-position training ledger, independent of Active43."""

    def __init__(self, starting_balance="10000", fee_rate="0.0006",
                 max_risk="0.005", max_notional="2000"):
        self.balance = number(starting_balance)
        self.starting_balance = self.balance
        self.fee_rate = number(fee_rate)
        self.max_risk = number(max_risk)
        self.max_notional = number(max_notional)
        self.position = None
        self.trades = []
        self.realized = D("0")

    def open(self, side, entry, stop, target, quantity, *, candle_time=None, position_id=None):
        if self.position is not None:
            raise ValueError("POSITION_ALREADY_OPEN")
        if side not in ("LONG", "SHORT"):
            raise ValueError("INVALID_SIDE")
        entry, stop, target, quantity = map(number, (entry, stop, target, quantity))
        if not ((stop < entry < target) if side == "LONG" else (target < entry < stop)):
            raise ValueError("INVALID_STOPS")
        if self.balance <= self.starting_balance * D("0.9"):
            raise ValueError("DRAWDOWN_LIMIT")
        notional = entry * quantity
        if notional > min(self.max_notional, self.balance):
            raise ValueError("POSITION_SIZE_LIMIT")
        entry_fee = notional * self.fee_rate
        stop_loss = abs(entry - stop) * quantity
        exit_fee_at_stop = stop * quantity * self.fee_rate
        if stop_loss + entry_fee + exit_fee_at_stop > self.balance * self.max_risk:
            raise ValueError("RISK_LIMIT")
        if self.balance < entry_fee:
            raise ValueError("INSUFFICIENT_BALANCE")
        if candle_time is not None and (type(candle_time) is not int or candle_time <= 0):
            raise ValueError("INVALID_CANDLE_TIME")
        self.balance -= entry_fee
        self.position = Position(side, quantity, entry, stop, target, entry_fee, candle_time, position_id)
        return self.position

    def close(self, price, *, reason="MANUAL", closed_at=None):
        price = number(price)
        position = self.position
        if position is None:
            raise ValueError("NO_POSITION")
        sign = D("1") if position.side == "LONG" else D("-1")
        gross = sign * (price - position.entry) * position.quantity
        exit_fee = price * position.quantity * self.fee_rate
        net = gross - position.entry_fee - exit_fee
        self.balance += gross - exit_fee
        self.realized += net
        trade = dict(side=position.side, entry=position.entry, exit=price,
                     quantity=position.quantity, gross=gross,
                     fees=position.entry_fee + exit_fee, net=net,
                     id=position.id, opened_at=position.entry_candle_time,
                     closed_at=closed_at, reason=reason, stop=position.stop, target=position.target)
        self.trades.append(trade)
        self.position = None
        return trade

    def on_closed_candle(self, high, low, close, *, candle_time=None):
        """Conservative SL-first execution if both levels touched in one candle.

        Offline model only; not an exchange stop or guaranteed fill.
        """
        high, low, close = map(number, (high, low, close))
        if low > high or not low <= close <= high:
            raise ValueError("INVALID_CANDLE")
        p = self.position
        if p is None:
            return None
        if p.entry_candle_time is not None:
            if type(candle_time) is not int or candle_time <= p.entry_candle_time:
                raise ValueError("CANDLE_NOT_AFTER_ENTRY")
        stop_hit = low <= p.stop if p.side == "LONG" else high >= p.stop
        target_hit = high >= p.target if p.side == "LONG" else low <= p.target
        if stop_hit:
            return self.close(p.stop)
        if target_hit:
            return self.close(p.target)
        return None

    def validate(self):
        """Reject damaged persisted accounting; never reset a bad journal."""
        if (self.starting_balance != D('10000') or self.fee_rate != D('0.0006')
                or self.max_risk != D('0.005') or self.max_notional != D('2000')):
            raise ValueError('CORRUPT_JOURNAL')
        if not self.balance.is_finite() or not self.realized.is_finite():
            raise ValueError('CORRUPT_JOURNAL')
        total = D('0')
        for t in self.trades:
            side, qty, entry, exit_price = t['side'], number(t['quantity']), number(t['entry']), number(t['exit'])
            if side not in ('LONG','SHORT'):
                raise ValueError('CORRUPT_JOURNAL')
            gross = (exit_price-entry)*qty*(1 if side=='LONG' else -1)
            fees = (entry+exit_price)*qty*self.fee_rate
            if (t['gross'],t['fees'],t['net']) != (gross,fees,gross-fees):
                raise ValueError('CORRUPT_JOURNAL')
            total += t['net']
        p = self.position
        if p:
            if (p.side not in ('LONG','SHORT') or p.entry_fee != p.entry*p.quantity*self.fee_rate
                    or not ((p.stop < p.entry < p.target) if p.side=='LONG' else (p.target < p.entry < p.stop))):
                raise ValueError('CORRUPT_JOURNAL')
            for v in (p.quantity,p.entry,p.stop,p.target,p.entry_fee):
                number(v)
        if self.realized != total or self.balance != self.starting_balance+total-(p.entry_fee if p else 0):
            raise ValueError('CORRUPT_JOURNAL')
