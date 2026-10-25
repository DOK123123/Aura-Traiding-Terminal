"""OFF-only rebaseline must never activate paper or synthesize trades."""
import asyncio
from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch
import pytest
from app.active43.core import initial, SOURCE
from app.active43.service import Service
from app.active43.strategies import config
from app.automated.engine import DemoError
from app.lab.models import Bar, digest


class Store:
    durable = True
    backend = 'test'
    def __init__(self, state):
        self.state = deepcopy(state)
        self.revision = 5
        self.events = []
    async def load(self, now):
        return dict(state=deepcopy(self.state), revision=self.revision, last_saved_at=now)
    async def lookup(self, key):
        return None
    async def commit(self, revision, state, events, key):
        assert revision == self.revision
        self.state = deepcopy(state)
        self.events.extend(events)
        self.revision += 1
        return dict(state=deepcopy(state), duplicate=False)


def run(state, expected_revision=5, error=None):
    cfg=config('SR_BOUNCE','5m')
    store=Store(state)
    svc=Service(store=store,cfg=cfg,clock=lambda: 600000)
    bars=[Bar(i*300,Decimal('100'),Decimal('101'),Decimal('99'),Decimal('100'),Decimal('1')) for i in range(1001)]
    # Fresh end must match fixed test clock (600000); 1000 bars ending 599700.
    bars=[Bar(299700+i*300,Decimal('100'),Decimal('101'),Decimal('99'),Decimal('100'),Decimal('1')) for i in range(1001)]
    async def snapshot():
        if error:raise DemoError(error)
        return bars,dict(source=SOURCE,signal_at=600000,source_sha256=digest([b.data() for b in bars])),600000
    svc.snapshot=snapshot
    with patch('app.active43.service.scheduler_configured',return_value=True):
        try:
            result=asyncio.run(svc.control('REBASELINE','a'*32,expected_revision))
            return store,result,None
        except DemoError as exc:
            return store,None,exc.code


def test_off_rebaseline_preserves_off_and_audits():
    s=initial(300000,config('SR_BOUNCE','5m'))
    s['mode']='OFF'
    store,result,error=run(s)
    assert error is None
    assert result['exchange_execution'] is False
    assert store.state['mode']=='OFF'
    assert store.state['watermark']==600000
    assert store.state['data_recovery_armed'] is False
    assert store.state['last_anchor_ohlcv'] is not None
    assert store.state['last_bar_hash']==digest(store.state['last_anchor_ohlcv'])
    assert [e['kind'] for e in store.events]==['CONTROL','BASELINE']
    assert all(e['kind'] not in ('OPEN','CLOSE','SIGNAL') for e in store.events)


@pytest.mark.parametrize('mode', ['ON','PAUSED','EMERGENCY'])
def test_rebaseline_rejects_any_non_off_mode(mode):
    s=initial(300000,config('SR_BOUNCE','5m'))
    s['mode']=mode
    store,result,error=run(s)
    assert error=='OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT'
    assert store.revision==5


def test_rebaseline_rejects_stale_revision():
    s=initial(300000,config('SR_BOUNCE','5m'))
    store,result,error=run(s,expected_revision=4)
    assert error=='CONCURRENT_UPDATE'
    assert store.revision==5


def test_rebaseline_rejects_unavailable_market():
    s=initial(300000,config('SR_BOUNCE','5m'))
    store,result,error=run(s,error='MARKET_UNAVAILABLE')
    assert error=='MARKET_UNAVAILABLE'
    assert store.revision==5


def test_rebaseline_rejects_armed_recovery():
    s=initial(300000,config('SR_BOUNCE','5m'))
    s['data_recovery_armed']=True
    store,result,error=run(s)
    assert error=='OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT'
    assert store.revision==5
