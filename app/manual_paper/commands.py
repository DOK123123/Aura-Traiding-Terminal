"""Network-free commands. Request identity excludes changing market evidence."""
from .core import number
from .store import ManualStore


class ManualCommands:
    def __init__(self, store: ManualStore):
        self.store = store
        self.validate_quote = lambda q: None

    @staticmethod
    def arguments(side, quantity, stop, target, *, entry_limit=None, analyst_at=None):
        # Canonical numeric identities: 0.01 and 0.010 are the same intent.
        args = dict(side=side, quantity=format(number(quantity).normalize(),'f'),
                    stop=format(number(stop).normalize(),'f'), target=format(number(target).normalize(),'f'))
        if entry_limit is not None:
            args['entry_limit'] = format(number(entry_limit).normalize(),'f')
        if analyst_at is not None:
            args['analyst_at'] = analyst_at
        return args

    @staticmethod
    def _quote(quote):
        if not isinstance(quote, dict) or quote.get('source') != 'Bitget USDT-M Futures':
            raise ValueError('SOURCE_MISMATCH')
        if type(quote.get('time')) is not int:
            raise ValueError('INVALID_QUOTE')
        return number(quote['price']), quote['time']

    def open(self, request_id, side, quantity, stop, target, quote, *, entry_limit=None,
             analyst_at=None, expires_at_ms=None):
        args = self.arguments(side,quantity,stop,target,entry_limit=entry_limit,analyst_at=analyst_at)
        def run(ledger):
            self.validate_quote(quote)
            price, stamp = self._quote(quote)
            if entry_limit is not None and (price > number(entry_limit) if side == 'LONG' else price < number(entry_limit)):
                raise ValueError('ENTRY_PRICE_MOVED')
            p = ledger.open(side, price, stop, target, quantity, candle_time=stamp, position_id=request_id)
            return dict(id=p.id, side=p.side, quantity=str(p.quantity), entry=str(p.entry),
                        stop=str(p.stop), target=str(p.target), candle_time=stamp)
        quote_ms = quote.get('time') if isinstance(quote,dict) else None
        # Supabase checks quote_ms after waiting for its transaction lock. Fence
        # it by the scenario deadline too, without changing the RPC/schema.
        if expires_at_ms is not None and quote_ms is not None:
            quote_ms = min(quote_ms, expires_at_ms - 5000)
        return self.store.execute(request_id,'OPEN',args,run,quote_ms=quote_ms)

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
        return self.store.execute(request_id,'CLOSE',args,run,quote_ms=quote.get('time') if isinstance(quote,dict) else None)
