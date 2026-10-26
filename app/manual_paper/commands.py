"""Network-free commands. Request identity excludes changing market evidence."""
from .core import number
from .store import ManualStore


class ManualCommands:
    def __init__(self, store: ManualStore):
        self.store = store
        self.validate_quote = lambda q: None

    @staticmethod
    def arguments(side, quantity, stop, target):
        # Canonical numeric identities: 0.01 and 0.010 are the same intent.
        return dict(side=side, quantity=format(number(quantity).normalize(),'f'),
                    stop=format(number(stop).normalize(),'f'), target=format(number(target).normalize(),'f'))

    @staticmethod
    def _quote(quote):
        if not isinstance(quote, dict) or quote.get('source') != 'Bitget USDT-M Futures':
            raise ValueError('SOURCE_MISMATCH')
        if type(quote.get('time')) is not int:
            raise ValueError('INVALID_QUOTE')
        return number(quote['price']), quote['time']

    def open(self, request_id, side, quantity, stop, target, quote):
        args = self.arguments(side,quantity,stop,target)
        def run(ledger):
            self.validate_quote(quote)
            price, stamp = self._quote(quote)
            p = ledger.open(side, price, stop, target, quantity, candle_time=stamp, position_id=request_id)
            return dict(id=p.id, side=p.side, quantity=str(p.quantity), entry=str(p.entry),
                        stop=str(p.stop), target=str(p.target), candle_time=stamp)
        return self.store.execute(request_id,'OPEN',args,run)

    def close(self, request_id, quote, position_id=None, reason='MANUAL'):
        args = dict(position_id=position_id, reason=reason)
        def run(ledger):
            self.validate_quote(quote)
            price, stamp = self._quote(quote)
            p = ledger.position
            if p is None:
                raise ValueError('NO_POSITION')
            if position_id is not None and p.id != position_id:
                raise ValueError('POSITION_NOT_FOUND')
            if p.entry_candle_time is not None and stamp < p.entry_candle_time:
                raise ValueError('QUOTE_BEFORE_ENTRY')
            trade = ledger.close(price, reason=reason, closed_at=stamp)
            return {k:str(v) if hasattr(v,'is_finite') else v for k,v in trade.items()}
        return self.store.execute(request_id,'CLOSE',args,run)
