"""Offline integration of real reducer/service, never live market injection."""
from copy import deepcopy
import time
import pytest
from app.manual_preview.signal_service import SignalService
from app.hunter.market import SOURCE
def fixture():
    return dict(strategy='TREND_PULLBACK', direction='LONG', frame='15m',
                structure={'pivot_time': 900, 'kind': 'LOW'}, score=75,
                checks=[{'code': 'TREND', 'passed': True}, {'code': 'CANDLE', 'passed': False}],
                rejection=['CANDLE'], valid_until=3000, entry=100, sl=95, tp=110, net_rr=1.7)



class MemoryStore:
    def __init__(self):
        self.version, self.records, self.events = 0, {}, {}
    def rpc(self, action, data=None):
        if action == 'load':
            return {'version': self.version, 'records': deepcopy(list(self.records.values()))}
        assert data['version'] == self.version
        self.records.update({r['id']: deepcopy(r) for r in data['records']})
        self.events.update({e['id']: deepcopy(e) for e in data['events']})
        self.version += 1
        return {'version': self.version}


def quote(now):
    return dict(source=SOURCE, bid=99.99, ask=100, last=100, time=now, received_at=now)


def test_server_500_ticks_watch_stale_and_restore():
    db = MemoryStore(); service = SignalService(None, db)
    c = fixture(); c.update(state='REJECTED',valid_until=time.time()+10000)
    at = time.time()
    for tick in range(500):
        service.apply([c], {'15m': quote(at+tick)}, at+tick)
    assert len(service.records) == len(db.events) == 1
    identity = next(iter(service.records))
    c['checks'][1]['passed'] = True; c['rejection'] = []
    service.apply([c], {'15m': quote(at+500)}, at+500)
    assert service.records[identity]['status'] == 'WATCH'
    assert len(db.events) == 2
    restarted = SignalService(None, db); restarted.restore()
    assert restarted.records == service.records
    # Browser cache fails closed before the worker persists the stale transition.
    assert service.view(at+506)['records'][0]['status'] == 'UNKNOWN'
    restarted.apply([], {}, at+506)
    assert restarted.records[identity]['status'] == 'UNKNOWN'
    assert restarted.records[identity]['current_plan'] is None
    restarted.apply([c], {'15m': quote(at+507)}, at+507)
    assert restarted.records[identity]['status'] == 'UNKNOWN' and len(db.events) == 3


def test_structural_change_and_locked_price_breach():
    db = MemoryStore(); service = SignalService(None, db); c = fixture()
    c.update(valid_until=3000, state='WATCH', rejection=[]);c['checks'][1]['passed']=True
    service.apply([c], {'15m':quote(1000)},1000)
    old = next(iter(service.records))
    q = quote(1001);q.update(bid=94.99,ask=95,last=95)
    service.apply([c],{'15m':q},1001)
    assert service.records[old]['status']=='INVALIDATED'
    c['structure']={'pivot_time':1800,'kind':'LOW'}
    service.apply([c],{'15m':quote(1002)},1002)
    assert len(service.records)==2
