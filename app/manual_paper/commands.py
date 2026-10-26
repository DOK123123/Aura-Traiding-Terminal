"""Offline virtual trade command orchestration.

Only pass server-verified quote objects from the Bitget adapter. This service
is deliberately not exposed as a production route. No exchange execution.
"""
from .core import number
from .store import ManualStore


class ManualCommands:
    def __init__(self, store: ManualStore):
        self.store = store

    @staticmethod
    def _quote(quote):
        if not isinstance(quote, dict) or quote.get("source") != "Bitget USDT-M Futures":
            raise ValueError("SOURCE_MISMATCH")
        if quote.get("timeframe") != 900 or type(quote.get("time")) is not int:
            raise ValueError("INVALID_QUOTE")
        return number(quote["price"]), quote["time"]

    def open(self, request_id, side, quantity, stop, target, quote):
        price, stamp = self._quote(quote)
        args = dict(side=side, quantity=str(quantity), stop=str(stop),
                    target=str(target), quote_time=stamp, quote_price=str(price))
        def run(ledger):
            position = ledger.open(side, price, stop, target, quantity, candle_time=stamp)
            return dict(side=position.side, quantity=str(position.quantity),
                        entry=str(position.entry), stop=str(position.stop),
                        target=str(position.target), candle_time=stamp)
        return self.store.execute(request_id, "OPEN", args, run)

    def close(self, request_id, quote):
        price, stamp = self._quote(quote)
        args = dict(quote_time=stamp, quote_price=str(price))
        def run(ledger):
            if ledger.position is not None and ledger.position.entry_candle_time is not None:
                if stamp < ledger.position.entry_candle_time:
                    raise ValueError("QUOTE_BEFORE_ENTRY")
            trade = ledger.close(price)
            return {key: str(value) for key, value in trade.items()}
        return self.store.execute(request_id, "CLOSE", args, run)
