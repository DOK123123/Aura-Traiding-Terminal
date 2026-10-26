"""Isolated, offline manual-paper accounting prototype. No exchange or database I/O.

Not connected to production API/UI. Every price must be an independently
validated closed-candle quote before a caller invokes open/mark/close.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

D = Decimal


def number(value):
    try:
        result = D(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("INVALID_NUMBER") from None
    if not result.is_finite() or result <= 0:
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

    def open(self, side, entry, stop, target, quantity):
        if self.position is not None:
            raise ValueError("POSITION_ALREADY_OPEN")
        if side not in ("LONG", "SHORT"):
            raise ValueError("INVALID_SIDE")
        entry, stop, target, quantity = map(number, (entry, stop, target, quantity))
        if not ((stop < entry < target) if side == "LONG" else (target < entry < stop)):
            raise ValueError("INVALID_STOPS")
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
        self.balance -= entry_fee
        self.position = Position(side, quantity, entry, stop, target, entry_fee)
        return self.position

    def close(self, price):
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
                     fees=position.entry_fee + exit_fee, net=net)
        self.trades.append(trade)
        self.position = None
        return trade

    def on_closed_candle(self, high, low, close):
        """Conservative SL-first execution if both levels touched in one candle.

        Offline model only; not an exchange stop or guaranteed fill.
        """
        high, low, close = map(number, (high, low, close))
        if low > high or not low <= close <= high:
            raise ValueError("INVALID_CANDLE")
        p = self.position
        if p is None:
            return None
        stop_hit = low <= p.stop if p.side == "LONG" else high >= p.stop
        target_hit = high >= p.target if p.side == "LONG" else low <= p.target
        if stop_hit:
            return self.close(p.stop)
        if target_hit:
            return self.close(p.target)
        return None
