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


def test_current_evidence_and_last_watch_confirmation_are_not_initial_snapshot():
    service=SignalService(None,MemoryStore());c=fixture()
    service.apply([c],{'15m':quote(1000)},1000)
    row=next(iter(service.records.values()));initial=deepcopy(row['initial'])
    assert row['current_checks'][1]['passed'] is False
    c['score']=100;c['checks'][1]['passed']=True;c['rejection']=[]
    service.apply([c],{'15m':quote(1001)},1001)
    row=next(iter(service.records.values()))
    assert row['initial']==initial and row['current_checks'][1]['passed'] is True
    assert row['last_confirmed_at']==row['last_evaluated_at']==1001
    assert row['plan_absence_reasons']==[]
    service.apply([],{},1002)
    row=next(iter(service.records.values()))
    assert row['status']=='UNKNOWN' and row['score']==100
    assert row['current_checks'][1]['passed'] is True and row['last_confirmed_at']==1001


def test_current_episode_survives_200_newer_historical_rows_in_api_window():
    service=SignalService(None,MemoryStore());c=fixture()
    service.apply([c],{'15m':quote(1000)},1000)
    active=deepcopy(next(iter(service.records.values())))
    for i in range(210):
        r=deepcopy(active);r.update(id=f'{i:064x}',status='EXPIRED',detected_at=1000+i)
        service.records[r['id']]=r
    view=service.view(1000)
    assert len(view['records'])==200 and view['records'][0]['id']==active['id']
    assert view['records'][0]['status']=='CANDIDATE'
    pinned=f'{0:064x}'
    assert pinned not in {r['id'] for r in view['records']}
    assert pinned in {r['id'] for r in service.view(1000,[pinned])['records']}


def test_silent_worker_gap_cannot_resume_same_watch_on_fresh_recovery():
    service=SignalService(None,MemoryStore());c=fixture()
    c.update(state='WATCH',score=100,rejection=[]);c['checks'][1]['passed']=True
    service.apply([c],{'15m':quote(1000)},1000)
    identity=next(iter(service.records))
    assert service.view(1006)['records'][0]['status']=='UNKNOWN'
    # No explicit exception/apply([], ...) occurred during this silent pause.
    service.apply([c],{'15m':quote(1006)},1006)
    assert service.records[identity]['status']=='UNKNOWN'
    service.apply([c],{'15m':quote(1007)},1007)
    assert service.records[identity]['status']=='UNKNOWN'
    c['structure']={'pivot_time':1800}
    service.apply([c],{'15m':quote(1008)},1008)
    assert service.view(1008)['records'][0]['status']=='WATCH'


def test_structure_replacement_records_exact_terminal_cause():
    service=SignalService(None,MemoryStore());c=fixture()
    c.update(state='WATCH',score=100,rejection=[]);c['checks'][1]['passed']=True
    service.apply([c],{'15m':quote(1000)},1000)
    old=next(iter(service.records))
    c['structure']={'pivot_time':1800}
    service.apply([c],{'15m':quote(1001)},1001)
    assert service.records[old]['status']=='INVALIDATED'
    assert service.records[old]['history'][-1]['reason']=='STRUCTURE_REPLACED'
    assert any(r['status']=='WATCH' for r in service.records.values())


def test_api_preserves_specific_candidate_absence_reason():
    service=SignalService(None,MemoryStore());c=fixture()
    service.apply([c],{'15m':quote(1000)},1000)
    view=service.view(1000)
    row=view['records'][0]
    assert row['status']=='CANDIDATE' and row['current_plan'] is None
    assert 'CANDLE' in row['plan_absence_reasons']
    assert row['plan_absence_reasons']==service.records[row['id']]['plan_absence_reasons']


def test_regime_api_fails_closed_for_stale_or_missing_frame():
    service=SignalService(None,MemoryStore());c=fixture()
    regime={'state':'TREND_UP','closed_at':900,'metrics':{'adx14':30}}
    c['market_regime']=regime
    service.apply([c],{'15m':quote(1000)},1000)
    assert service.view(1000)['market_regimes']['15m']==regime
    assert all(v['state']=='UNKNOWN' for f,v in service.view(1000)['market_regimes'].items() if f!='15m')
    assert service.view(1006)['market_regimes']['15m']['state']=='UNKNOWN'
