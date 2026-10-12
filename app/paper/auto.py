"""Network-free Auto Paper coordinator: atomic decision, watermark and virtual entry."""
from dataclasses import dataclass
from decimal import Decimal
import json
import logging
import uuid

from .engine import precise
from .safety import require_preflight,preflight
from .models import PaperError, Window, STEPS, decimal, text

STRATEGY_VERSION = 'HISTORICAL_PATTERN_V1_DEFAULTS'
AUDIT_LIMIT = 2000
AUDIT_DAYS = 30
SIGNAL_FAILURE_LIMIT = 3
SIGNAL_RETRY_DELAY_MS = 15000
logger = logging.getLogger(__name__)
TRANSIENT = {'STALE_DATA','MARKET_GAP','SOURCE_MISMATCH','TIMEFRAME_MISMATCH','MARKET_TIMEOUT',
             'MARKET_UNAVAILABLE','SIGNAL_UNAVAILABLE','SNAPSHOT_MISMATCH','INVALID_MARKET_DATA'}
REASONS = TRANSIENT | {'OFF','AUTO_OFF','NO_SIGNAL','DUPLICATE_SIGNAL','POSITION_ALREADY_OPEN',
 'RISK_LIMIT','POSITION_SIZE_LIMIT','POSITION_LIMIT','INSUFFICIENT_BALANCE','INVALID_SL','INVALID_TP',
 'STOPS_UNAVAILABLE','INVALID_STOPS','INVALID_DATA','QUOTE_CHANGED','ACTIVATION_BASELINE',
 'MISSED_CANDLE_NO_ENTRY','RESTART_REQUIRES_RESUME','OWNER_NOT_CONFIGURED','SIGNAL_ERROR','ERROR',
 'WAITING_FOR_NEW_CANDLE','CONFIG_CHANGED','SIGNAL_RETRY_EXHAUSTED'}


@dataclass(frozen=True)
class Signal:
    symbol: str
    timeframe: str
    source: str
    candle_time: int
    direction: str
    confidence: Decimal | None
    strategy_version: str = STRATEGY_VERSION
    stop_loss: str | None = None
    take_profit: str | None = None

    def validate(self, window: Window):
        if self.symbol != window.symbol or self.source != window.source:
            raise PaperError('SOURCE_MISMATCH')
        if self.timeframe != window.timeframe:
            raise PaperError('TIMEFRAME_MISMATCH')
        if type(self.candle_time) is not int or self.candle_time != window.bars[-1].time:
            raise PaperError('SNAPSHOT_MISMATCH')
        if self.direction not in ('LONG','SHORT','WAIT') or self.strategy_version != STRATEGY_VERSION:
            raise PaperError('SIGNAL_ERROR')
        if self.confidence is not None and (not isinstance(self.confidence,Decimal) or not self.confidence.is_finite() or not 0 <= self.confidence <= 100):
            raise PaperError('SIGNAL_ERROR')


class Auto:
    def __init__(self, engine, *, restart=True):
        self.engine,self.store = engine,engine.store
        with self.store.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS auto_decisions (
                id TEXT PRIMARY KEY, recorded_at INTEGER NOT NULL, candle_time INTEGER NOT NULL,
                data TEXT NOT NULL)''')
            stored = self.store.get(db,'auto_paper')
            if stored is None:
                state = dict(status='OFF',enabled=False,configured=False,symbol='BTCUSDT',timeframe='15m',
                             source='Binance · Spot',fallback_policy='SKIP',generation=0,watermarks={},
                             last_processed_candle=None,last_signal=None,last_action='OFF',last_rejection_reason=None,
                             manual_resume=False,signal_retry=None)
                self._save(db,state)
            else:
                try:
                    state=json.loads(stored)
                    if (state['status'] not in ('OFF','ON','PAUSED','ERROR') or type(state['enabled']) is not bool
                            or state['symbol'] != 'BTCUSDT' or state['timeframe'] not in STEPS
                            or state['fallback_policy'] not in ('SKIP','PAPER_SETTINGS')
                            or type(state['generation']) is not int or state['generation'] < 0
                            or type(state['configured']) is not bool or type(state['manual_resume']) is not bool
                            or (state['status']=='OFF') != (not state['enabled'])
                            or (state['enabled'] and not state['configured'])
                            or not isinstance(state['source'],str) or not 1 <= len(state['source']) <= 120
                            or not isinstance(state['watermarks'],dict)
                            or any(k not in STEPS or type(v) is not int or v < 0 or v%STEPS[k] for k,v in state['watermarks'].items())):
                        raise ValueError()
                    retry=state.get('signal_retry')
                    if retry is not None and (not isinstance(retry,dict)
                            or set(retry)!={'candle_time','timeframe','source','failures','next_attempt_at'}
                            or retry['timeframe']!=state['timeframe'] or retry['source']!=state['source']
                            or type(retry['candle_time']) is not int or retry['candle_time']<0
                            or retry['candle_time']%STEPS[state['timeframe']]
                            or type(retry['failures']) is not int or not 1<=retry['failures']<=SIGNAL_FAILURE_LIMIT
                            or type(retry['next_attempt_at']) is not int or retry['next_attempt_at']<0):
                        raise ValueError()
                except (ValueError,TypeError,KeyError):
                    raise PaperError('CORRUPT_JOURNAL') from None
                if restart and state['enabled']:
                    state.update(status='PAUSED',manual_resume=True,last_rejection_reason='RESTART_REQUIRES_RESUME',
                                 last_action='PAUSED',generation=state['generation']+1)
                    self._save(db,state)
            self._prune(db)

    def _state(self,db):
        return json.loads(self.store.get(db,'auto_paper'))

    def _save(self,db,state):
        self.store.set(db,'auto_paper',json.dumps(state))

    def state(self):
        with self.store.transaction(write=False) as db:
            state=self._state(db)
            state['safety_preflight']=preflight(self.engine._settings(db),state['fallback_policy'],opened=self.store.trades(db,opened=True))
            state['decisions']=[json.loads(r[0]) for r in db.execute('SELECT data FROM auto_decisions ORDER BY candle_time DESC,recorded_at DESC LIMIT 100')]
            state['decisions_retained']=db.execute('SELECT COUNT(*) FROM auto_decisions').fetchone()[0]
            return state

    def _prune(self,db):
        db.execute('DELETE FROM auto_decisions WHERE recorded_at<?',(self.engine.clock()-AUDIT_DAYS*86400000,))
        db.execute('''DELETE FROM auto_decisions WHERE id IN (SELECT id FROM auto_decisions
            ORDER BY recorded_at DESC,candle_time DESC LIMIT -1 OFFSET ?)''',(AUDIT_LIMIT,))

    def _record(self,db,state,window,candle_time,reason,signal=None,trade=None):
        if reason not in REASONS:
            reason='SIGNAL_ERROR'
        ident=f'{window.symbol}:{window.timeframe}:{candle_time}'
        data=dict(timestamp=(candle_time+STEPS[window.timeframe])*1000,recorded_at=self.engine.clock(),
                  symbol=window.symbol,timeframe=window.timeframe,candle_time=candle_time,
                  signal_result=signal.direction if signal else None,confidence=text(signal.confidence) if signal else None,
                  auto_status=state['status'],auto_enabled=state['enabled'],trade_opened=trade is not None,
                  trade_id=trade['id'] if trade else None,rejection_reason=None if trade else reason,
                  action='OPENED' if trade else 'SKIPPED',strategy_version=STRATEGY_VERSION,source=window.source)
        db.execute('INSERT OR IGNORE INTO auto_decisions VALUES (?,?,?,?)',(ident,self.engine.clock(),candle_time,json.dumps(data)))
        state['watermarks'][window.timeframe]=max(candle_time,state['watermarks'].get(window.timeframe,-1))
        retry=state.get('signal_retry')
        if retry and candle_time>=retry['candle_time']:
            state['signal_retry']=None
        state.update(last_processed_candle=data['timestamp'],last_signal=data['signal_result'],
                     last_action=data['action'],last_rejection_reason=data['rejection_reason'])
        self._save(db,state);self._prune(db)

    def configure(self, enabled: bool, window: Window | None = None, *, fallback_policy='SKIP'):
        if type(enabled) is not bool or fallback_policy not in ('SKIP','PAPER_SETTINGS'):
            raise PaperError('INVALID_DATA')
        if enabled:
            if window is None:
                raise PaperError('INVALID_MARKET_DATA')
            window.validate(self.engine.clock())
        with self.store.transaction() as db:
            state=self._state(db)
            if enabled:
                require_preflight(self.engine._settings(db),fallback_policy,entry=window.bars[-1].close,opened=self.store.trades(db,opened=True))
            if not enabled:
                state.update(enabled=False,status='OFF',manual_resume=False,generation=state['generation']+1,last_action='OFF',signal_retry=None)
                self._save(db,state)
            elif state['status']=='ON' and (state['symbol'],state['timeframe'],state['source'],state['fallback_policy']) == (window.symbol,window.timeframe,window.source,fallback_policy):
                pass # Idempotent UI retry must not continually skip subsequent candles.
            else:
                state.update(enabled=True,status='ON',configured=True,manual_resume=False,symbol=window.symbol,
                             timeframe=window.timeframe,source=window.source,fallback_policy=fallback_policy,
                             generation=state['generation']+1,signal_retry=None)
                self._record(db,state,window,window.bars[-1].time,'ACTIVATION_BASELINE')
        return self.state()

    def needs_signal(self,window):
        state=self.state()
        retry=state.get('signal_retry')
        if retry and window.bars[-1].time<retry['candle_time']:
            return False
        if retry and retry['failures']>=SIGNAL_FAILURE_LIMIT:
            return False
        if retry and window.bars[-1].time==retry['candle_time'] and self.engine.clock()<retry['next_attempt_at']:
            return False
        return (state['enabled'] and not state['manual_resume'] and state['status']!='ERROR'
                and state['timeframe']==window.timeframe and state['source']==window.source
                and window.bars[-1].time>state['watermarks'].get(window.timeframe,-1))

    def fail(self,code,window=None,generation=None):
        if code not in REASONS:
            code='SIGNAL_ERROR'
        with self.store.transaction() as db:
            state=self._state(db)
            if generation is not None and state['generation'] != generation:
                return state
            if code=='SIGNAL_UNAVAILABLE':
                if not state['enabled'] or state['manual_resume'] or state['status']=='ERROR':
                    return state
                if window is None:
                    state.update(status='PAUSED',manual_resume=True,last_action='PAUSED',last_rejection_reason=code)
                    self._save(db,state)
                    return state
                try:
                    window.validate(self.engine.clock())
                except PaperError:
                    # No valid candle to retry; never mark an uncomputed signal consumed.
                    state.update(status='PAUSED',last_action='PAUSED',last_rejection_reason=code)
                    self._save(db,state)
                    return state
                bar=window.bars[-1]
                if ((window.symbol,window.timeframe,window.source)!=(state['symbol'],state['timeframe'],state['source'])
                        or bar.time<=state['watermarks'].get(window.timeframe,-1)):
                    return state
                retry=state.get('signal_retry')
                if retry and bar.time<retry['candle_time']:
                    return state
                failures=retry['failures']+1 if retry else 1
                failures=min(failures,SIGNAL_FAILURE_LIMIT)
                exhausted=failures>=SIGNAL_FAILURE_LIMIT
                state.update(status='PAUSED',manual_resume=exhausted,last_action='PAUSED',
                             last_rejection_reason='SIGNAL_RETRY_EXHAUSTED' if exhausted else code,
                             signal_retry=dict(candle_time=bar.time,timeframe=window.timeframe,source=window.source,
                                               failures=failures,next_attempt_at=self.engine.clock()+SIGNAL_RETRY_DELAY_MS*failures))
                # Persist retry metadata only: a failed read is not a final candle decision.
                self._save(db,state)
                logger.warning('Auto Paper signal read failed: candle=%s failures=%s/%s status=%s',
                               bar.time,failures,SIGNAL_FAILURE_LIMIT,state['last_rejection_reason'])
                return state
            if state['enabled']:
                manual=code not in TRANSIENT or bool(state.get('signal_retry') and state['manual_resume'])
                state.update(status='ERROR' if code=='SIGNAL_ERROR' else 'PAUSED',manual_resume=manual,
                             last_action='PAUSED',last_rejection_reason=code)
                self._save(db,state)
                if window is not None:
                    bar=window.bars[-1]
                    if (window.symbol==state['symbol'] and window.timeframe==state['timeframe']
                            and type(bar.time) is int and bar.time%STEPS[window.timeframe]==0
                            and (bar.time+STEPS[window.timeframe])*1000<=self.engine.clock()
                            and bar.time>state['watermarks'].get(window.timeframe,-1)):
                        retry=state.get('signal_retry')
                        if not retry:
                            self._record(db,state,window,bar.time,code)
        return self.state()

    @precise
    def process(self,window:Window,signal:Signal | None,generation:int):
        try:
            window.validate(self.engine.clock())
        except PaperError as error:
            return self.fail(error.code,window)
        with self.store.transaction() as db:
            state=self._state(db)
            if (window.symbol,window.timeframe)!=(state['symbol'],state['timeframe']):
                raise PaperError('TIMEFRAME_MISMATCH')
            last=state['watermarks'].get(window.timeframe,-1)
            bar=window.bars[-1];step=STEPS[window.timeframe]
            if bar.time<=last:
                return dict(state,duplicate=True) # Persistent watermark survives log rotation and old REST responses.
            if state['generation']!=generation:
                return dict(state,obsolete=True) # OFF/ON/scope changed while server evaluation was in flight.
            retry=state.get('signal_retry')
            if retry and bar.time<retry['candle_time']:
                return dict(state,obsolete=True) # An older REST snapshot cannot replace a pending newer signal.
            if retry and signal is None and (bar.time==retry['candle_time'] or state['manual_resume']
                                             or retry['failures']>=SIGNAL_FAILURE_LIMIT):
                return state # Cooldown/exhaustion/restart must not consume the pending signal.
            if window.source!=state['source']:
                state.update(status='PAUSED',last_rejection_reason='SOURCE_MISMATCH')
                self._record(db,state,window,bar.time,'SOURCE_MISMATCH');return state
            if last>=0 and window.bars[0].time>last+step:
                state.update(status='PAUSED',manual_resume=True)
                self._record(db,state,window,bar.time,'MARKET_GAP');return state
            for old in window.bars:
                if last<old.time<bar.time:
                    self._record(db,state,window,old.time,'MISSED_CANDLE_NO_ENTRY' if state['enabled'] else 'AUTO_OFF')
            reason='AUTO_OFF'
            if not state['enabled']:
                pass
            elif state['manual_resume'] or state['status']=='ERROR':
                reason=state.get('last_rejection_reason') or 'ERROR'
            else:
                state['status']='ON'
                try:
                    if signal is None:
                        raise PaperError('SIGNAL_ERROR')
                    signal.validate(window)
                    if signal.direction=='WAIT':
                        reason='NO_SIGNAL'
                    elif self.store.trades(db,opened=True):
                        reason='POSITION_ALREADY_OPEN'
                    elif signal.stop_loss is None or signal.take_profit is None:
                        if state['fallback_policy']=='SKIP':
                            reason='STOPS_UNAVAILABLE'
                        else:
                            reason='ENTER'
                    else:
                        reason='ENTER'
                    if reason=='ENTER':
                        sign=1 if signal.direction=='LONG' else -1
                        for field,code in ((signal.stop_loss,'INVALID_SL'),(signal.take_profit,'INVALID_TP')):
                            if field is not None:
                                try:value=decimal(field,positive=True)
                                except PaperError:raise PaperError(code) from None
                                if (code=='INVALID_SL' and sign*(bar.close-value)<=0) or (code=='INVALID_TP' and sign*(value-bar.close)<=0):
                                    raise PaperError(code)
                        ident=f'{window.symbol}:{window.timeframe}:{bar.time}'
                        payload=dict(request_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'aura-auto:'+ident)),
                                     symbol=window.symbol,timeframe=window.timeframe,direction=signal.direction,
                                     expected_source=window.source,expected_candle_time=bar.time,expected_price=text(bar.close),
                                     position_size=None,stop_loss=signal.stop_loss,take_profit=signal.take_profit,
                                     entry_reason='Confirmed existing Historical Pattern signal; '+state['fallback_policy'],signal_id=ident)
                        meta=dict(signal_source='HISTORICAL_PATTERN_V1',signal_direction=signal.direction,
                                  signal_timestamp=(bar.time+step)*1000,signal_confidence=text(signal.confidence),
                                  strategy_version=signal.strategy_version,market_data_source=window.source,
                                  stop_policy='STRATEGY' if signal.stop_loss is not None and signal.take_profit is not None else 'PAPER_SETTINGS')
                        # SAVEPOINT removes any failed risk/open side effects, while retaining the audit rejection.
                        db.execute('SAVEPOINT auto_entry')
                        try:trade=self.engine._open_in_transaction(db,payload,window,auto_metadata=meta)
                        except BaseException:
                            db.execute('ROLLBACK TO auto_entry');db.execute('RELEASE auto_entry');raise
                        db.execute('RELEASE auto_entry')
                        self._record(db,state,window,bar.time,'NO_SIGNAL',signal,trade)
                        return state
                except PaperError as error:
                    reason=error.code if error.code in REASONS else 'SIGNAL_ERROR'
                    if reason in TRANSIENT or reason=='SIGNAL_ERROR':
                        state.update(status='ERROR' if reason=='SIGNAL_ERROR' else 'PAUSED',manual_resume=reason=='SIGNAL_ERROR')
            self._record(db,state,window,bar.time,reason,signal)
            return state
