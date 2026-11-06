"""Server-owned Aura 5 episodes, independent of open tabs and account execution."""
import asyncio
from copy import deepcopy
import time

from app.hunter.market import SOURCE, STEPS, fresh_quote
from .explainable import from_store
from .lifecycle import reduce_signal, scenario_id, TERMINAL


class SignalService:
    def __init__(self, observer, store):
        self.observer, self.store = observer, store
        self.records = {}
        self.version = 0
        self.error = 'STARTING'
        self.updated_at = 0
        self.last_quotes = {}

    def restore(self):
        rows, after, version = {}, '', None
        for _ in range(101):
            value = self.store.rpc('load', {'after': after})
            if version is not None and value['version'] != version:
                raise ValueError('SIGNAL_CONCURRENT_RESTORE')
            version = value['version']
            batch = value['records']
            rows.update({r['id']: r for r in batch})
            if len(batch) < 50:
                self.records, self.version = rows, version
                return
            after = batch[-1]['id']
        raise ValueError('SIGNAL_RETENTION_LIMIT')

    def apply(self, candidates: list[dict], quotes: dict, now: float):
        current = {scenario_id(c): c for c in candidates if c.get('structure')}
        records = deepcopy(self.records)
        changed, events = [], []
        for identity in sorted(set(records) | set(current)):
            previous = records.get(identity)
            if previous and previous['status'] in TERMINAL:
                continue
            c = current.get(identity)
            q = quotes.get((c or previous)['frame'], {})
            trusted = c is not None and c.get('state') != 'UNKNOWN' and fresh_quote(q, now)
            # Replaced market structure cannot silently retarget an old locked plan.
            replaced = c is None and any(x['frame'] == previous['frame'] and
                        x['strategy'] == previous['strategy'] and x['direction'] == previous['direction']
                        for x in current.values()) and fresh_quote(q, now)
            if c is None:
                c = previous['initial']
            plan = previous.get('watch_plan') if previous else None
            breached = False
            if plan and fresh_quote(q, now):
                price = q['bid' if c['direction'] == 'LONG' else 'ask']
                breached = not min(plan['sl'], plan['tp']) < price < max(plan['sl'], plan['tp'])
            row, event = reduce_signal(previous, c, now, trusted=trusted or replaced,
                                       invalidated=breached or replaced)
            if row is None:
                continue
            row['refreshed_at'] = min(q.get('time', now), q.get('received_at', now)) if trusted else now
            records[identity] = row
            changed.append(row)
            if event:
                events.append(event)
        if changed:
            response = self.store.rpc('commit', {'version': self.version, 'records': changed, 'events': events})
            if response.get('conflict'):
                self.restore()
                raise ValueError('SIGNAL_CONCURRENT_UPDATE')
            self.version = response['version']
        self.records, self.last_quotes = records, deepcopy(quotes)
        self.updated_at, self.error = now, None

    def view(self, now: float, selected: list[str] | None = None) -> dict:
        rows = sorted(self.records.values(), key=lambda r: (r['detected_at'], r['id']), reverse=True)[:200]
        present = {r['id'] for r in rows}
        rows += [self.records[i] for i in (selected or []) if i in self.records and i not in present]
        result = deepcopy(rows)
        for r in result:
            if r['status'] not in TERMINAL:
                if self.error or now-self.updated_at > 5 or not fresh_quote(self.last_quotes.get(r['frame'], {}), now):
                    r['status'], r['current_plan'] = 'UNKNOWN', None
                elif now >= r['valid_until']:
                    r['status'], r['current_plan'] = 'EXPIRED', None
        return {'scope': 'AURA5_SIGNAL_LOCK_V1', 'storage': 'SUPABASE', 'server_time': now,
                'updated_at': self.updated_at, 'error': self.error, 'records': result,
                'quotes': deepcopy(self.last_quotes), 'edge': 'NO_EDGE_FOUND', 'exchange_execution': False}

    async def run(self):
        restored = False
        while True:
            try:
                if not restored:
                    await asyncio.to_thread(self.restore)
                    # A process gap is unobserved, never silently resume active episodes.
                    await asyncio.to_thread(self.apply, [], {}, time.time())
                    restored = True
                response = await self.observer.market.get('ticker')
                now = time.time()
                if len(response['data']) != 1 or response['data'][0].get('symbol') != 'BTCUSDT':
                    raise ValueError('MARKET_IDENTITY_MISMATCH')
                raw = response['data'][0]
                q = dict(source=SOURCE, bid=float(raw['bidPr']), ask=float(raw['askPr']),
                         last=float(raw['lastPr']), time=float(raw['ts'])/1000, received_at=now)
                if not fresh_quote(q, now):
                    raise ValueError('STALE_QUOTE')
                quotes = {frame: q for frame in STEPS}
                rows = await asyncio.to_thread(from_store, self.observer.store, quotes, now,
                                               not self.observer.error)
                await asyncio.to_thread(self.apply, rows, quotes, time.time())
            except asyncio.CancelledError:
                raise
            except Exception:
                self.error = 'SIGNAL_LOCK_UNAVAILABLE'
                if restored:
                    try:
                        await asyncio.to_thread(self.apply, [], {}, time.time())
                    except Exception:
                        self.error = 'SIGNAL_STORAGE_UNAVAILABLE'
            await asyncio.sleep(1)
