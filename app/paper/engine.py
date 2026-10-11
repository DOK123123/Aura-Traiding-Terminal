"""Local, network-free virtual ledger. No exchange execution capability."""
from decimal import Decimal, localcontext
from functools import wraps
import hashlib
import json
import time
import uuid

from .models import Settings, Window, PaperError, STEPS, decimal, money, quantity, text, MONEY_TICK
from .storage import Store

D = Decimal


def precise(function):
    @wraps(function)
    def run(*args, **kwargs):
        with localcontext() as context:
            context.prec = 64
            return function(*args, **kwargs)
    return run


def fee(price: Decimal, size: Decimal, pct: Decimal) -> Decimal:
    return money(price * size * pct / 100, ceiling=True)


def checked_label(value: str, maximum: int = 300) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum or any(ord(c) < 32 for c in value):
        raise PaperError('INVALID_DATA')
    return value.strip()


class Engine:
    @precise
    def __init__(self, store: Store, settings: Settings | None = None, clock=None):
        self.store = store
        self.clock = clock or (lambda: int(time.time() * 1000))
        with store.transaction() as db:
            version = store.get(db, 'version')
            if version is None:
                if (db.execute('SELECT COUNT(*) FROM meta').fetchone()[0] or store.trades(db)
                        or db.execute('SELECT COUNT(*) FROM curve').fetchone()[0]):
                    raise PaperError('CORRUPT_JOURNAL')
                settings = settings or Settings.from_env()
                settings.validate()
                for key, value in [('version','1'), ('settings',json.dumps(settings.to_dict())),
                                   ('balance',text(settings.starting_balance)), ('peak',text(settings.starting_balance)),
                                   ('maximum_drawdown_pct','0'), ('maximum_drawdown_usdt','0'), ('close_sequence','0')]:
                    store.set(db, key, value)
                self._point(db, self.clock())
            elif version != '1':
                raise PaperError('CORRUPT_JOURNAL')
            try:
                settings = self._settings(db)
                for key in ('balance','peak','maximum_drawdown_pct','maximum_drawdown_usdt'):
                    value = D(store.get(db,key))
                    if not value.is_finite() or value != money(value) or (key != 'balance' and value < 0):
                        raise ValueError()
                if D(store.get(db,'peak')) < settings.starting_balance:
                    raise ValueError()
                trades = store.trades(db)
                sequence = int(store.get(db,'close_sequence'))
                closed_sequences = sorted(t['close_seq'] for t in trades if t['status'] == 'CLOSED')
                if sequence != len(closed_sequences) or closed_sequences != list(range(1,len(closed_sequences)+1)):
                    raise ValueError()
                for row,trade in zip(db.execute('SELECT * FROM trades ORDER BY seq'),trades):
                    if any(row[key] != trade.get(key) for key in ('id','status','symbol','timeframe','source','signal_id','close_seq')):
                        raise ValueError()
                for trade in trades:
                    commands = list(db.execute('SELECT key,kind,digest FROM requests WHERE trade_id=?',(trade['id'],)))
                    if sum(row['kind'] == 'open' for row in commands) != 1 or sum(row['kind'] == 'close' for row in commands) > 1:
                        raise ValueError()
                    for row in commands:
                        if (row['kind'] not in ('open','close') or str(uuid.UUID(row['key'])) != row['key']
                                or len(row['digest']) != 64 or any(c not in '0123456789abcdef' for c in row['digest'])):
                            raise ValueError()
                if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                    raise ValueError()
                points = list(db.execute('SELECT * FROM curve ORDER BY seq'))
                if not points:
                    raise ValueError()
                previous_peak = settings.starting_balance
                previous_maximum = D(0)
                maximum_loss = D(0)
                for point in points:
                    values = {key:D(point[key]) if point[key] is not None else None for key in
                              ('balance','equity','peak','drawdown_pct','maximum_drawdown_pct')}
                    if any(v is not None and (not v.is_finite() or v != money(v)) for v in values.values()):
                        raise ValueError()
                    peak,maximum = values['peak'],values['maximum_drawdown_pct']
                    if peak is None or maximum is None or peak < previous_peak or maximum < previous_maximum:
                        raise ValueError()
                    equity,drawdown = values['equity'],values['drawdown_pct']
                    expected_drawdown = None if equity is None else money(max(D(0),peak-equity)/peak*100)
                    if equity is not None:
                        maximum_loss = max(maximum_loss,peak-equity)
                    if drawdown != expected_drawdown or (drawdown is not None and maximum < drawdown):
                        raise ValueError()
                    previous_peak,previous_maximum = peak,maximum
                if (previous_peak != D(store.get(db,'peak')) or previous_maximum != D(store.get(db,'maximum_drawdown_pct'))
                        or maximum_loss != D(store.get(db,'maximum_drawdown_usdt'))):
                    raise ValueError()
                expected = settings.starting_balance
                for trade in trades:
                    self._validate_trade(trade)
                    if trade['direction'] not in ('LONG','SHORT') or trade['status'] not in ('OPEN','CLOSED'):
                        raise ValueError()
                    expected += D(trade['realized_pnl']) if trade['status'] == 'CLOSED' else -D(trade['entry_fee'])
                if money(expected) != self._balance(db):
                    raise ValueError()
            except (KeyError, ValueError, TypeError, ArithmeticError, PaperError):
                raise PaperError('CORRUPT_JOURNAL') from None

    @staticmethod
    def _validate_trade(trade):
        if trade['symbol'] != 'BTCUSDT' or trade['timeframe'] not in STEPS or trade['signal_source'] != 'MANUAL':
            raise ValueError()
        checked_label(trade['source'],120)
        checked_label(trade['entry_reason'])
        size,price = D(trade['position_size']),D(trade['entry_price'])
        rate = D(trade['commission_pct'])
        values = [D(trade[k]) for k in ('position_size','entry_price','stop_loss','take_profit','entry_fee',
                  'reserved_notional','risk_usdt','risk_budget_usdt','planned_risk_reward','mark_price')]+[rate]
        if any(not v.is_finite() for v in values) or size <= 0 or price <= 0 or not 0 <= rate <= 10:
            raise ValueError()
        direction = trade['direction']
        if direction not in ('LONG','SHORT') or trade['status'] not in ('OPEN','CLOSED'):
            raise ValueError()
        sign = 1 if direction == 'LONG' else -1
        stop,target = D(trade['stop_loss']),D(trade['take_profit'])
        if min(stop,target,D(trade['mark_price'])) <= 0 or sign*(price-stop) <= 0 or sign*(target-price) <= 0:
            raise ValueError()
        step = STEPS[trade['timeframe']]
        for key in ('entry_time','entry_price_time','observed_at','mark_time','last_candle_time','processed_at'):
            if type(trade[key]) is not int or trade[key] < 0:
                raise ValueError()
        if (trade['last_candle_time'] % step or trade['mark_time'] != (trade['last_candle_time']+step)*1000
                or trade['entry_price_time'] % (step*1000) or trade['entry_price_time'] > trade['entry_time']
                or trade['mark_time'] < trade['entry_price_time']):
            raise ValueError()
        if size != quantity(size) or D(trade['entry_fee']) != fee(price,size,rate) or D(trade['reserved_notional']) != money(price*size,ceiling=True):
            raise ValueError()
        if trade['status'] == 'CLOSED':
            exit_price = D(trade['exit_price'])
            if not exit_price.is_finite() or exit_price <= 0:
                raise ValueError()
            gross = Engine._gross(trade,exit_price)
            exit_fee = fee(exit_price,size,rate)
            if (D(trade['exit_fee']) != exit_fee or D(trade['gross_price_pnl']) != gross
                    or D(trade['realized_pnl']) != money(gross-D(trade['entry_fee'])-exit_fee)
                    or D(trade['commissions']) != D(trade['entry_fee'])+exit_fee
                    or D(trade['pnl_pct']) != money(D(trade['realized_pnl'])/D(trade['reserved_notional'])*100)
                    or type(trade['exit_time']) is not int or trade['exit_time'] < trade['entry_time']
                    or type(trade['close_seq']) is not int or trade['close_seq'] <= 0):
                raise ValueError()
        elif D(trade['commissions']) != D(trade['entry_fee']):
            raise ValueError()

    def _settings(self, db):
        return Settings.from_dict(json.loads(self.store.get(db, 'settings')))

    def _balance(self, db):
        return D(self.store.get(db, 'balance'))

    def _equity(self, db, now, *, valuation_at=None):
        reference = now if valuation_at is None else valuation_at
        if valuation_at is not None:
            # Do not combine a historical candle with future entry fees/settlements.
            for trade in self.store.trades(db):
                if trade['entry_time'] > reference or (trade['exit_time'] is not None and trade['exit_time'] > reference):
                    return None
        result = self._balance(db)
        for trade in self.store.trades(db, opened=True):
            if (trade.get('market_error') or now-trade['observed_at'] > 30000
                    or reference-trade['mark_time'] > 2*STEPS[trade['timeframe']]*1000
                    or trade['mark_time'] > reference):
                return None
            price, size = D(trade['mark_price']), D(trade['position_size'])
            result += self._gross(trade, price) - fee(price, size, D(trade['commission_pct']))
        return money(result)

    @staticmethod
    def _gross(trade, price):
        sign = 1 if trade['direction'] == 'LONG' else -1
        return money(sign*(price-D(trade['entry_price']))*D(trade['position_size']))

    def _point(self, db, now, market_at=None, *, historical=False):
        equity = self._equity(db, now, valuation_at=market_at if historical else None)
        peak = D(self.store.get(db,'peak'))
        maximum = D(self.store.get(db,'maximum_drawdown_pct'))
        maximum_usdt = D(self.store.get(db,'maximum_drawdown_usdt'))
        drawdown = None
        if equity is not None:
            peak = max(peak, equity)
            loss = max(D(0),peak-equity)
            drawdown = money(loss/peak*100) if peak > 0 else D(0)
            maximum = max(maximum,drawdown)
            maximum_usdt = max(maximum_usdt,loss)
            self.store.set(db,'peak',text(peak))
            self.store.set(db,'maximum_drawdown_pct',text(maximum))
            self.store.set(db,'maximum_drawdown_usdt',text(maximum_usdt))
        db.execute('''INSERT INTO curve(recorded_at,market_at,balance,equity,peak,drawdown_pct,maximum_drawdown_pct)
                      VALUES (?,?,?,?,?,?,?)''', (now,market_at,text(self._balance(db)),text(equity),text(peak),text(drawdown),text(maximum)))

    @staticmethod
    def digest(payload):
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def _replay(self, db, key, kind, payload):
        try:
            if str(uuid.UUID(key)) != key:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise PaperError('INVALID_REQUEST_ID') from None
        row = db.execute('SELECT * FROM requests WHERE key=?',(key,)).fetchone()
        if row is None:
            return None
        if row['kind'] != kind or row['digest'] != self.digest(payload):
            raise PaperError('IDEMPOTENCY_CONFLICT')
        return json.loads(db.execute('SELECT data FROM trades WHERE id=?',(row['trade_id'],)).fetchone()[0])

    def replay(self, key: str, kind: str, payload: dict) -> dict | None:
        with self.store.transaction(write=False) as db:
            return self._replay(db,key,kind,payload)

    def _record_request(self, db, key, kind, payload, trade):
        db.execute('INSERT INTO requests(key,kind,digest,trade_id) VALUES (?,?,?,?)',
                   (key,kind,self.digest(payload),trade['id']))

    @precise
    def configure(self, values: dict) -> dict:
        settings = Settings.from_dict(values)
        with self.store.transaction() as db:
            previous = self._settings(db)
            if settings.starting_balance != previous.starting_balance:
                if self.store.trades(db):
                    raise PaperError('STARTING_BALANCE_LOCKED')
                self.store.set(db,'balance',text(settings.starting_balance))
                self.store.set(db,'peak',text(settings.starting_balance))
                self.store.set(db,'maximum_drawdown_pct','0')
                self.store.set(db,'maximum_drawdown_usdt','0')
                db.execute('DELETE FROM curve')
            self.store.set(db,'settings',json.dumps(settings.to_dict()))
            if not self.store.trades(db):
                db.execute('DELETE FROM curve')
                self._point(db,self.clock())
        return settings.to_dict()

    @precise
    def open(self, payload: dict, window: Window) -> dict:
        now = self.clock()
        window.validate(now)
        with self.store.transaction() as db:
            replay = self._replay(db,payload['request_id'],'open',payload)
            if replay is not None:
                return replay
            if (payload['symbol'],payload['timeframe'],payload['expected_source']) != (window.symbol,window.timeframe,window.source):
                raise PaperError('SOURCE_MISMATCH')
            bar = window.bars[-1]
            if payload['expected_candle_time'] != bar.time or decimal(payload['expected_price'],positive=True) != bar.close:
                raise PaperError('QUOTE_CHANGED')
            self._advance(db,window,now)
            settings = self._settings(db)
            opened = self.store.trades(db,opened=True)
            if len(opened) >= settings.maximum_simultaneous_positions:
                raise PaperError('POSITION_LIMIT')
            if payload.get('signal_id') and db.execute('SELECT 1 FROM trades WHERE signal_id=?',(payload['signal_id'],)).fetchone():
                raise PaperError('DUPLICATE_SIGNAL')
            direction = payload['direction']
            if direction not in ('LONG','SHORT'):
                raise PaperError('INVALID_DIRECTION')
            reason = checked_label(payload['entry_reason'])
            signal = payload.get('signal_id')
            if signal is not None:
                checked_label(signal,120)
            price = bar.close
            sign = 1 if direction == 'LONG' else -1
            stop = decimal(payload['stop_loss'],positive=True) if payload.get('stop_loss') is not None else price*(1-sign*settings.stop_loss_pct/100)
            target = decimal(payload['take_profit'],positive=True) if payload.get('take_profit') is not None else price*(1+sign*settings.take_profit_pct/100)
            if (sign*(price-stop) <= 0 or sign*(target-price) <= 0 or min(stop,target) <= 0
                    or max(stop,target) > D('1000000000000')):
                raise PaperError('INVALID_STOPS')
            equity = self._equity(db,now)
            if equity is None:
                raise PaperError('STALE_DATA')
            if equity <= 0:
                raise PaperError('INSUFFICIENT_BALANCE')
            free = self._balance(db)-sum((D(t['reserved_notional']) for t in opened),D(0))
            budget = equity*settings.risk_per_trade_pct/100
            unit_risk = abs(price-stop)+(price+stop)*settings.commission_pct/100
            if payload.get('position_size') is None:
                size = quantity(min((budget-3*MONEY_TICK)/unit_risk,
                                    settings.maximum_position_size_usdt/price,
                                    (free-2*MONEY_TICK)/(price*(1+settings.commission_pct/100))))
            else:
                raw = decimal(payload['position_size'],positive=True)
                size = quantity(raw)
                if raw != size:
                    raise PaperError('INVALID_POSITION_SIZE')
            if size <= 0:
                raise PaperError('INSUFFICIENT_BALANCE')
            notional = money(price*size,ceiling=True)
            entry_fee = fee(price,size,settings.commission_pct)
            risk = money(abs(price-stop)*size,ceiling=True)+entry_fee+fee(stop,size,settings.commission_pct)
            reward = money(abs(target-price)*size)-entry_fee-fee(target,size,settings.commission_pct)
            if notional > settings.maximum_position_size_usdt:
                raise PaperError('POSITION_SIZE_LIMIT')
            if notional+entry_fee > free:
                raise PaperError('INSUFFICIENT_BALANCE')
            if risk > budget:
                raise PaperError('RISK_LIMIT')
            if reward <= 0:
                raise PaperError('INVALID_STOPS')
            trade = dict(id=str(uuid.uuid4()),symbol=window.symbol,direction=direction,entry_price=text(price),entry_time=now,
                         entry_price_time=(bar.time+STEPS[window.timeframe])*1000,position_size=text(size),stop_loss=text(stop),
                         take_profit=text(target),exit_price=None,exit_time=None,entry_reason=reason,exit_reason=None,
                         signal_source='MANUAL',signal_id=signal,timeframe=window.timeframe,source=window.source,
                         commission_pct=text(settings.commission_pct),entry_fee=text(entry_fee),exit_fee=None,
                         commissions=text(entry_fee),realized_pnl=None,pnl_pct=None,gross_price_pnl=None,status='OPEN',
                         reserved_notional=text(notional),risk_usdt=text(risk),risk_budget_usdt=text(money(budget)),
                         planned_risk_reward=text(money(reward/risk)),mark_price=text(price),mark_time=(bar.time+STEPS[window.timeframe])*1000,
                         last_candle_time=bar.time,observed_at=window.observed_at,market_error=None,
                         fill_model='VERIFIED_CLOSED_CANDLE',processed_at=now)
            self.store.set(db,'balance',text(money(self._balance(db)-entry_fee)))
            self.store.save(db,trade)
            self._record_request(db,payload['request_id'],'open',payload,trade)
            self._point(db,now,trade['mark_time'])
            return trade

    def _settle(self, db, trade, price, exit_time, reason, now):
        exit_fee = fee(price,D(trade['position_size']),D(trade['commission_pct']))
        gross = self._gross(trade,price)
        net = money(gross-D(trade['entry_fee'])-exit_fee)
        sequence = int(self.store.get(db,'close_sequence'))+1
        self.store.set(db,'close_sequence',str(sequence))
        trade.update(status='CLOSED',exit_price=text(price),exit_time=exit_time,exit_reason=reason,
                     processed_at=now,exit_fee=text(exit_fee),commissions=text(D(trade['entry_fee'])+exit_fee),
                     gross_price_pnl=text(gross),realized_pnl=text(net),pnl_pct=text(money(net/D(trade['reserved_notional'])*100)),
                     close_seq=sequence,market_error=None)
        self.store.set(db,'balance',text(money(self._balance(db)+gross-exit_fee)))
        self.store.save(db,trade)
        return trade

    def _advance(self, db, window, now):
        step = STEPS[window.timeframe]
        trades = [t for t in self.store.trades(db,opened=True) if (t['symbol'],t['timeframe']) == (window.symbol,window.timeframe)]
        eligible = []
        for trade in trades:
            if trade['source'] != window.source:
                trade['market_error'] = 'SOURCE_MISMATCH'
            elif window.bars[-1].time < trade['last_candle_time']:
                trade['market_error'] = 'OUT_OF_ORDER'
            elif window.bars[0].time > trade['last_candle_time']+step:
                trade['market_error'] = 'MARKET_GAP'
            else:
                same = next((b for b in window.bars if b.time == trade['last_candle_time']),None)
                if same is not None and same.close != D(trade['mark_price']):
                    trade['market_error'] = 'CANDLE_CORRECTION'
                else:
                    trade.update(observed_at=window.observed_at,market_error=None)
                    eligible.append(trade)
            self.store.save(db,trade)
        for bar in window.bars:
            changed = False
            for trade in eligible:
                if trade['status'] != 'OPEN' or bar.time <= trade['last_candle_time']:
                    continue
                changed = True
                sign = 1 if trade['direction'] == 'LONG' else -1
                stop,target = D(trade['stop_loss']),D(trade['take_profit'])
                # Never inspect highs/lows made before the manual entry within its first overlapping bar.
                complete = bar.time*1000 >= trade['entry_time']
                low,high = (bar.low,bar.high) if complete else (bar.close,bar.close)
                stop_hit = low <= stop if sign == 1 else high >= stop
                target_hit = high >= target if sign == 1 else low <= target
                price = None
                reason = None
                if stop_hit:
                    price = (min(stop,bar.open) if sign == 1 else max(stop,bar.open)) if complete else bar.close
                    reason = 'STOP_LOSS_AMBIGUOUS' if target_hit else 'STOP_LOSS'
                elif target_hit:
                    price,reason = (target if complete else bar.close),'TAKE_PROFIT'
                trade.update(last_candle_time=bar.time,mark_price=text(bar.close),mark_time=(bar.time+step)*1000)
                if price is not None:
                    self._settle(db,trade,price,(bar.time+step)*1000,reason,now)
                else:
                    self.store.save(db,trade)
            if changed:
                self._point(db,now,(bar.time+step)*1000,historical=True)

    @precise
    def advance(self, window: Window) -> None:
        now = self.clock()
        window.validate(now)
        with self.store.transaction() as db:
            self._advance(db,window,now)

    @precise
    def close(self, trade_id: str, payload: dict, window: Window) -> dict:
        now = self.clock()
        window.validate(now)
        with self.store.transaction() as db:
            replay = self._replay(db,payload['request_id'],'close',dict(payload,trade_id=trade_id))
            if replay is not None:
                return replay
            row = db.execute('SELECT data FROM trades WHERE id=?',(trade_id,)).fetchone()
            if row is None:
                raise PaperError('POSITION_NOT_FOUND')
            trade = json.loads(row[0])
            if trade['status'] != 'OPEN':
                raise PaperError('POSITION_CLOSED')
            if (trade['symbol'],trade['timeframe'],trade['source']) != (window.symbol,window.timeframe,window.source):
                raise PaperError('SOURCE_MISMATCH')
            self._advance(db,window,now)
            trade = json.loads(db.execute('SELECT data FROM trades WHERE id=?',(trade_id,)).fetchone()[0])
            if trade['status'] == 'OPEN':
                reason = checked_label(payload['exit_reason'])
                if trade.get('market_error') in ('OUT_OF_ORDER','CANDLE_CORRECTION'):
                    raise PaperError('INVALID_MARKET_DATA')
                prefix = 'MANUAL_HISTORY_GAP' if trade.get('market_error') == 'MARKET_GAP' else 'MANUAL'
                trade = self._settle(db,trade,window.bars[-1].close,now,prefix+': '+reason,now)
                self._point(db,now,(window.bars[-1].time+STEPS[window.timeframe])*1000)
            self._record_request(db,payload['request_id'],'close',dict(payload,trade_id=trade_id),trade)
            return trade

    def scopes(self) -> list[tuple[str, str]]:
        with self.store.transaction(write=False) as db:
            return sorted({(t['symbol'],t['timeframe']) for t in self.store.trades(db,opened=True)})

    def trade(self, trade_id: str) -> dict:
        with self.store.transaction(write=False) as db:
            row = db.execute('SELECT data FROM trades WHERE id=?',(trade_id,)).fetchone()
            if row is None:
                raise PaperError('POSITION_NOT_FOUND')
            return json.loads(row[0])

    def unavailable(self, symbol: str, timeframe: str, code: str) -> None:
        with self.store.transaction() as db:
            changed = False
            for trade in self.store.trades(db,opened=True):
                if (trade['symbol'],trade['timeframe']) == (symbol,timeframe) and trade.get('market_error') != code:
                    trade['market_error'] = code
                    self.store.save(db,trade)
                    changed = True
            if changed:
                self._point(db,self.clock())

    def handle_signal(self, *args, **kwargs):
        raise PaperError('AUTOMATIC_EXECUTION_DISABLED')

    @precise
    def snapshot(self) -> dict:
        now = self.clock()
        with self.store.transaction(write=False) as db:
            settings = self._settings(db)
            trades = self.store.trades(db)
            opened = [t for t in trades if t['status'] == 'OPEN']
            closed = sorted((t for t in trades if t['status'] == 'CLOSED'),key=lambda t:t['close_seq'])
            pnl = [D(t['realized_pnl']) for t in closed]
            wins,losses = [p for p in pnl if p > 0],[p for p in pnl if p < 0]
            profit,loss = sum(wins,D(0)),-sum(losses,D(0))
            net = sum(pnl,D(0))
            average_win = profit/len(wins) if wins else None
            average_loss = loss/len(losses) if losses else None
            equity = self._equity(db,now)
            streak_win=streak_loss=max_win=max_loss=0
            for p in pnl:
                streak_win = streak_win+1 if p > 0 else 0
                streak_loss = streak_loss+1 if p < 0 else 0
                max_win,max_loss = max(max_win,streak_win),max(max_loss,streak_loss)
            for trade in opened:
                fresh = (not trade.get('market_error') and now-trade['observed_at'] <= 30000
                         and now-trade['mark_time'] <= 2*STEPS[trade['timeframe']]*1000)
                trade['data_status'] = 'FRESH' if fresh else trade.get('market_error') or 'STALE_DATA'
                trade['unrealized_pnl'] = text(self._gross(trade,D(trade['mark_price']))-D(trade['entry_fee'])-
                                              fee(D(trade['mark_price']),D(trade['position_size']),D(trade['commission_pct']))) if fresh else None
            count = db.execute('SELECT COUNT(*) FROM curve').fetchone()[0]
            curve = [dict(r) for r in db.execute('SELECT * FROM curve ORDER BY seq DESC LIMIT 500')][::-1]
            stats = dict(total_trades=len(closed),winning_trades=len(wins),losing_trades=len(losses),breakeven_trades=len(pnl)-len(wins)-len(losses),
                         win_rate=text(money(D(len(wins))/len(pnl)*100)) if pnl else None,gross_profit=text(profit),gross_loss=text(loss),net_pnl=text(net),
                         profit_factor=text(money(profit/loss)) if loss else None,average_win=text(money(average_win)) if average_win is not None else None,
                         average_loss=text(money(average_loss)) if average_loss is not None else None,
                         risk_reward=text(money(sum((D(t['planned_risk_reward']) for t in trades),D(0))/len(trades))) if trades else None,
                         realized_reward_risk=text(money(average_win/average_loss)) if average_win is not None and average_loss else None,
                         maximum_drawdown_pct=self.store.get(db,'maximum_drawdown_pct'),maximum_drawdown_usdt=self.store.get(db,'maximum_drawdown_usdt'),
                         current_balance=text(self._balance(db)),available_balance=text(self._balance(db)-sum((D(t['reserved_notional']) for t in opened),D(0))),
                         equity=text(equity),return_pct=text(money((equity/settings.starting_balance-1)*100)) if equity is not None else None,
                         consecutive_wins=streak_win,consecutive_losses=streak_loss,maximum_consecutive_wins=max_win,maximum_consecutive_losses=max_loss,
                         total_commissions=text(sum((D(t['commissions']) for t in trades),D(0))),open_positions=len(opened))
            return dict(paper=True,real_money_execution='DISABLED',automatic_signal_execution=False,settings=settings.to_dict(),statistics=stats,
                        open_positions=opened,closed_trades=closed[-100:][::-1],closed_trades_total=len(closed),journal_truncated=len(closed)>100,
                        equity_curve=curve,equity_curve_total=count,equity_curve_truncated=count>500,
                        persistence='SQLITE',persistence_warning='Render local filesystem is ephemeral unless PAPER_DB_PATH points to a persistent disk. Download backups.')
