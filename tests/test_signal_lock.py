"""Offline lifecycle/persistence/transport tests. No credentials or orders."""
import copy
import json
import sqlite3
import unittest
from app.manual_preview.signal_lock import advance, project, Service, VERSION, SOURCE, MODEL_HASH
from app.hunter.costs import risk_reward
from app.manual_preview.web_push import Sender, subscription

NOW = 1787464801


def sample(score=70, state='REJECTED'):
    checks = [{'code': 'CONDITION_' + str(i), 'passed': i < score // 5} for i in range(20)]
    quote = dict(source=SOURCE, bid=99.99, ask=100.01, last=100, time=NOW, received_at=NOW)
    costs = risk_reward(100.01, 95, 115, 'LONG', 3600, 4, .02)
    candidate = dict(version=VERSION, source=SOURCE, model_sha256=MODEL_HASH,
                     frame='1h', strategy='TREND_PULLBACK', direction='LONG',
                     manual_only=True, exchange_execution=False, statistical_status='UNVALIDATED',
                     probability_tp_before_sl=None, score=score, state=state, checks=checks,
                     rejection=[] if state == 'WATCH' else ['MISSING_CONFIRMATION'],
                     quote_time=NOW, quote_received_at=NOW, closed_at=NOW // 3600 * 3600,
                     valid_until=NOW // 3600 * 3600 + 3600,
                     entry=100.01, sl=95, tp=115, net_rr=costs['net_rr'], costs=costs)
    return candidate, {'1h': quote}


class DiskStore:
    """Disposable test DB only: never used as a Render persistence fallback."""
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('create table if not exists state (id integer primary key, version integer, payload text)')
        self.db.execute("insert or ignore into state values(1,0,'null')")
        self.db.commit()

    def load(self):
        v, s = self.db.execute('select version,payload from state where id=1').fetchone()
        return v, json.loads(s)

    def compare_and_swap(self, version, value):
        cursor = self.db.execute('update state set version=version+1,payload=? where id=1 and version=?',
                                 (json.dumps(value), version))
        self.db.commit()
        return cursor.rowcount == 1


class LifecycleTest(unittest.TestCase):
    def test_500_quotes_one_event_and_one_notice(self):
        c, quotes = sample()
        state = None
        for i in range(500):
            stamp = NOW + i
            c['quote_time'] = c['quote_received_at'] = stamp
            quotes['1h']['time'] = quotes['1h']['received_at'] = stamp
            c['score'] = (70, 75, 80)[i % 3]
            for j, condition in enumerate(c['checks']):
                condition['passed'] = j < c['score'] // 5
            state = advance(state, [c], quotes, stamp)
        self.assertEqual(len(state['events']), 1)
        self.assertEqual(len(state['notices']), 1)
        row = next(iter(state['events'].values()))
        self.assertEqual(row['initial_score'], 70)
        self.assertIsNone(project(row, NOW)['plan'])

    def test_promotion_unknown_and_terminal_invalidation(self):
        c, quotes = sample()
        state = advance(None, [c], quotes, NOW)
        c['state'], c['score'], c['rejection'] = 'WATCH', 100, []
        for check in c['checks']:
            check['passed'] = True
        state = advance(state, [c], quotes, NOW)
        row = next(iter(state['events'].values()))
        self.assertEqual(row['status'], 'WATCH')
        self.assertEqual(len(state['notices']), 2)
        self.assertIsNotNone(project(row, NOW)['plan'])
        stale = advance(state, [c], quotes, NOW + 6)
        self.assertEqual(next(iter(stale['events'].values()))['status'], 'UNKNOWN')
        self.assertIsNone(project(row, NOW + 6)['plan'])
        c['state'], c['score'], c['rejection'] = 'REJECTED', 80, ['CANCELLED_CONDITION']
        for i, check in enumerate(c['checks']):
            check['passed'] = i < 16
        c['quote_time'] = c['quote_received_at'] = NOW + 7
        quotes['1h']['time'] = quotes['1h']['received_at'] = NOW + 7
        state = advance(stale, [c], quotes, NOW + 7)
        row = next(iter(state['events'].values()))
        self.assertEqual(row['status'], 'INVALIDATED')
        self.assertIsNotNone(row['archive_plan'])
        self.assertIsNone(project(row, NOW)['plan'])
        self.assertEqual(len(state['notices']), 2)

    def test_expiry_and_score_hysteresis(self):
        c, quotes = sample()
        state = advance(None, [c], quotes, NOW)
        c['score'] = 65
        for i, check in enumerate(c['checks']):
            check['passed'] = i < 13
        state = advance(state, [c], quotes, NOW)
        self.assertEqual(next(iter(state['events'].values()))['status'], 'CANDIDATE')
        state = advance(state, [], {}, c['valid_until'])
        self.assertEqual(next(iter(state['events'].values()))['status'], 'EXPIRED')

    def test_no_fabricated_watch_or_candidate(self):
        for mutate in [lambda c,q: c.update(net_rr=1.4), lambda c,q: c.update(entry=101),
                      lambda c,q: c.update(state='REJECTED'), lambda c,q: c['checks'][0].update(passed=False),
                      lambda c,q: c.update(net_rr=99), lambda c,q: c['costs'].update(net_loss=.01)]:
            c, q = sample(100, 'WATCH')
            mutate(c, q)
            state = advance(None, [c], q, NOW)
            self.assertTrue(all(e['status'] != 'WATCH' for e in state['events'].values()))
        c, q = sample()
        q['1h']['source'] = 'FOREIGN'
        self.assertEqual(advance(None, [c], q, NOW)['events'], {})
        self.assertEqual(advance(None, [c], q, NOW, running=False)['events'], {})

    def test_restart_preserves_ids_and_dedup(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'disposable.sqlite'
            a = DiskStore(path)
            c, q = sample()
            rows = Service(a).step([c], q, NOW)
            a.db.close()
            b = DiskStore(path)
            again = Service(b).step([c], q, NOW)
            self.assertEqual(rows[0]['id'], again[0]['id'])
            self.assertEqual(len(b.load()[1]['notices']), 1)
            self.assertEqual(project(b.load()[1]['events'][rows[0]['id']], NOW + 6)['status'], 'UNKNOWN')
            b.db.close()

    def test_subscription_rejects_ssrf_and_keys(self):
        for url in ['http://fcm.googleapis.com/fcm/send/x', 'https://localhost/x',
                    'https://fcm.googleapis.com.evil.test/x', 'https://user:pass@fcm.googleapis.com/x']:
            with self.assertRaises(ValueError):
                subscription({'endpoint': url, 'keys': {}})

    def test_no_vapid_generation_or_default(self):
        with self.assertRaises(ValueError):
            Sender('', '', '')

    def test_watch_expiry_short_plan_and_terminal_dedup(self):
        c, q = sample(100, 'WATCH')
        c.update(direction='SHORT', entry=99.99, sl=105, tp=85)
        c['costs'] = risk_reward(99.99, 105, 85, 'SHORT', 3600, 4, .02)
        c['net_rr'] = c['costs']['net_rr']
        state = advance(None, [c], q, NOW)
        event = next(iter(state['events'].values()))
        self.assertEqual(event['status'], 'WATCH')
        self.assertGreater(project(event, NOW)['plan']['risk_usdt_per_btc'], 0)
        expired = advance(state, [], {}, c['valid_until'])
        self.assertEqual(next(iter(expired['events'].values()))['status'], 'EXPIRED')
        # A retried old observation cannot resurrect a terminal event.
        again = advance(expired, [c], q, NOW)
        self.assertEqual(next(iter(again['events'].values()))['status'], 'EXPIRED')
        self.assertEqual(len(again['notices']), 1)

    def test_atomic_conflict_retries_without_duplicate_event(self):
        class Conflicting:
            state = None
            count = 0
            def load(self):
                return self.count, self.state
            def compare_and_swap(self, version, state):
                self.count += 1
                self.state = state  # first writer committed before our CAS
                return self.count > 1
        c, q = sample()
        store = Conflicting()
        rows = Service(store).step([c], q, NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(store.state['notices']), 1)

    def test_transport_acceptance_is_not_device_delivery_and_errors_are_sanitized(self):
        import base64
        enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip('=')
        # Clearly dummy, structurally shaped test bytes. No real credentials.
        target = {'endpoint': 'https://fcm.googleapis.com/fcm/send/DUMMY_ONLY_NOT_REAL',
                  'keys': {'p256dh': enc(bytes([4]) + bytes(64)), 'auth': enc(bytes(16))}}
        for code, expected in [(201, 'ACCEPTED_NOT_DEVICE_CONFIRMED'), (410, 'GONE'),
                               (404, 'GONE'), (429, 'RETRY'), (503, 'RETRY')]:
            def fake(**kwargs):
                self.assertEqual(kwargs['ttl'], 60)
                self.assertEqual(kwargs['timeout'], 5)
                return type('Response', (), {'status_code': code})()
            sender = Sender('A' * 43, 'A' * 87, 'mailto:dummy@example.invalid', fake)
            self.assertEqual(sender.send(target, {'status': 'TEST'}, object()), expected)
        def broken(**kwargs):
            raise RuntimeError('DUMMY endpoint/private data must never be returned')
        sender = Sender('A' * 43, 'A' * 87, 'mailto:dummy@example.invalid', broken)
        self.assertEqual(sender.send(target, {}, object()), 'RETRY')


if __name__ == '__main__':
    unittest.main()
