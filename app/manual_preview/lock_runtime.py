"""Preview-only durable Signal Lock and delivery worker. Never an order worker."""
import asyncio
import copy
from contextlib import asynccontextmanager
import logging
import secrets
import time

from app.hunter.market import PublicMarket, SOURCE, STEPS, fresh_quote
from .explainable import from_store
from .lock_store import DurableLockStore, PushStore
from .signal_lock import advance, project
from .web_push import Sender, generate_vapid, no_redirect_session

log = logging.getLogger('aura.preview.signal_lock')


def structural(state: dict | None) -> tuple:
    """Persist all transitions immediately, checkpoint tick-only changes at 30s.

    This avoids rewriting the complete durable journal on every public quote.
    Every newly exposed event/transition is committed before it is published.
    """
    state = state or {'events': {}, 'notices': {}}
    return (tuple(sorted((k, e['status'], e.get('archive_plan') is not None)
                         for k, e in state['events'].items())), tuple(sorted(state['notices'])))


class Coordinator:
    def __init__(self, store, push_store=None, sender=None):
        self.store, self.push_store, self.sender = store, push_store, sender
        self.state = None
        self.version = None
        self.committed_structure = None
        self.checkpoint = 0
        self.updated_at = 0
        self.error = 'STARTING'
        self.quote = None
        self.queued = set()
        self.last_cleanup = 0
        self.delivery_error = None

    def process(self, candidates: list[dict], quotes: dict, now: float, running: bool) -> None:
        for _ in range(3):
            if self.version is None:
                self.version, self.state = self.store.load()
                self.committed_structure = structural(self.state)
            updated = advance(self.state, candidates, quotes, now, running)
            if structural(updated) != self.committed_structure or now-self.checkpoint >= 30:
                if not self.store.compare_and_swap(self.version, updated):
                    self.version = None
                    continue
                self.version += 1
                self.checkpoint = now
                self.committed_structure = structural(updated)
            self.state = updated
            self.updated_at, self.error = now, None
            return
        raise ValueError('SIGNAL_LOCK_WRITE_CONFLICT')

    def snapshot(self, now: float, running: bool = True) -> dict:
        healthy = running and self.error is None and 0 <= now-self.updated_at <= 7
        rows = []
        for value in (self.state or {}).get('events', {}).values():
            row = project(value, now)
            if not healthy and row['status'] not in ('EXPIRED', 'INVALIDATED'):
                row.update(status='UNKNOWN', plan=None)
            rows.append(row)
        rows.sort(key=lambda e: (e['detected_at'], e['id']), reverse=True)
        return {'enabled': True, 'ready': healthy, 'events': rows, 'error': None if healthy else 'LOCK_DATA_UNAVAILABLE',
                'updated_at': self.updated_at, 'quote': self.quote if fresh_quote(self.quote, now) else None,
                'execution_enabled': False, 'storage': 'DEDICATED_SUPABASE_PREVIEW'}

    def deliver(self, now: float) -> None:
        if not self.sender or not self.push_store or self.error:
            return
        # Replay of the durable outbox is safe; old intents never trigger alerts.
        for key, notice in (self.state or {}).get('notices', {}).items():
            if key in self.queued or not 0 <= now-notice['at'] < 60:
                continue
            event = self.state['events'].get(notice['event_id'])
            row = project(event, now) if event else None
            if not row or row['status'] != notice['status']:
                continue
            payload = {'event_id': row['id'], 'direction': row['direction'], 'frame': row['frame'],
                       'status': notice['status'], 'score': notice['score'], 'at': notice['at'],
                       'expires_at': min(row['valid_until'], notice['at']+60)}
            self.push_store.call('enqueue', payload)
            self.queued.add(key)
        session = no_redirect_session()
        try:
            for _ in range(4):
                lease = secrets.token_hex(16)
                job = self.push_store.call('claim', {'lease': lease})
                if not job:
                    break
                payload = job['payload']
                event = (self.state or {}).get('events', {}).get(payload['event_id'])
                row = project(event, time.time()) if event else None
                valid = (payload['status'] == 'TEST' or row and row['status'] == payload['status'])
                result = 'STALE'
                if valid and time.time() < payload['expires_at']:
                    result = self.sender.send(job['target'], payload, session)
                self.push_store.call('complete', {'id': job['id'], 'lease': lease, 'result': result})
        finally:
            session.close()
        if now-self.last_cleanup > 3600:
            self.push_store.call('cleanup')
            self.last_cleanup = now


def bootstrap(preview_store, push_enabled: bool) -> Coordinator:
    lock_store = DurableLockStore(preview_store)
    # Attestation + format check must succeed before constructing any worker.
    lock_store.load()
    push_store = sender = None
    if push_enabled:
        push_store = PushStore(preview_store)
        keys = push_store.call('config')
        if keys is None:
            # Server-side key creation; never changes any existing credentials.
            keys = push_store.call('bootstrap', generate_vapid())
        sender = Sender(keys['private'], keys['public'], keys['contact'])
    return Coordinator(lock_store, push_store, sender)


async def quote_once(client) -> dict:
    response = await PublicMarket(client).get('ticker')
    data = response['data']
    if len(data) != 1 or data[0].get('symbol') != 'BTCUSDT':
        raise ValueError('MARKET_IDENTITY_MISMATCH')
    q = data[0]
    result = {'source': SOURCE, 'bid': float(q['bidPr']), 'ask': float(q['askPr']),
              'last': float(q['lastPr']), 'time': float(q['ts'])/1000, 'received_at': time.time()}
    if not fresh_quote(result, time.time()):
        raise ValueError('STALE_OR_UNTRUSTED_QUOTE')
    return result


async def run(app, preview_store, push_enabled: bool) -> None:
    worker = None
    while True:
        try:
            if worker is None:
                worker = await asyncio.to_thread(bootstrap, preview_store, push_enabled)
                app.state.signal_lock = worker
            observer = getattr(app.state, 'preview_signals', None)
            task = getattr(app.state, 'preview_signals_task', None)
            running = observer is not None and task is not None and not task.done() and not observer.error
            now = time.time()
            quotes, candidates = {}, []
            if running:
                try:
                    quote = await quote_once(app.state.preview_public_client)
                    worker.quote = quote
                    quotes = {frame: quote for frame in STEPS}
                    now = time.time()
                    candidates = await asyncio.to_thread(from_store, observer.store, quotes, now, True)
                except (ValueError, KeyError, TypeError, OSError):
                    quotes, candidates = {}, []
            await asyncio.to_thread(worker.process, candidates, quotes, now, running)
        except asyncio.CancelledError:
            if worker:
                worker.error = 'WORKER_STOPPED'
            raise
        except Exception:
            if worker:
                worker.error = 'LOCK_STORAGE_OR_DELIVERY_UNAVAILABLE'
                worker.version = None
            # Never log exception text, endpoints, key material or subscribers.
            log.warning('PREVIEW_SIGNAL_LOCK_UNAVAILABLE')
        await asyncio.sleep(2 if worker and worker.error is None else 10)


async def delivery_run(app) -> None:
    while True:
        worker = getattr(app.state,'signal_lock',None)
        if worker and worker.sender:
            try:
                await asyncio.to_thread(worker.deliver,time.time())
                worker.delivery_error = None
            except asyncio.CancelledError:
                raise
            except Exception:
                worker.delivery_error = 'PUSH_QUEUE_UNAVAILABLE'
                log.warning('PREVIEW_PUSH_QUEUE_UNAVAILABLE')
        await asyncio.sleep(2)


@asynccontextmanager
async def lock_lifespan(app, preview_store, enabled: bool, push_enabled: bool):
    app.state.signal_lock = None
    app.state.signal_lock_enabled = enabled
    task = asyncio.create_task(run(app, preview_store, push_enabled)) if enabled else None
    app.state.signal_lock_task = task
    delivery_task = asyncio.create_task(delivery_run(app)) if enabled and push_enabled else None
    app.state.signal_push_task = delivery_task
    try:
        yield
    finally:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if delivery_task:
            delivery_task.cancel()
            await asyncio.gather(delivery_task,return_exceptions=True)


def snapshot(app, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    worker = getattr(app.state, 'signal_lock', None)
    task = getattr(app.state, 'signal_lock_task', None)
    if worker is None:
        return {'enabled': bool(getattr(app.state, 'signal_lock_enabled', False)), 'ready': False,
                'events': [], 'error': 'LOCK_STARTING_OR_UNAVAILABLE', 'execution_enabled': False}
    return worker.snapshot(now, task is not None and not task.done())
