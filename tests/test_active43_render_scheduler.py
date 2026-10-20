"""Isolated worker scheduling and safety; no production keys, accounts or orders."""
import asyncio
import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from app.active43.service import Service
from app.automated.engine import DemoError
from scripts import active43_render_scheduler as worker
from tests.test_active43 import setup


@pytest.mark.parametrize('now,expected',[(0,120),(120,300),(121,299),(419,1),(420,300),(1792497372,48)])
def test_next_deadline_uses_existing_utc_five_minute_phase(now,expected):
    assert worker.next_delay(now)==expected


@pytest.mark.parametrize('now',[float('nan'),float('inf'),-1])
def test_invalid_clock_fails_closed(now):
    with pytest.raises(DemoError,match='WORKER_CLOCK_INVALID'):worker.next_delay(now)


def test_default_disabled_never_constructs_trading_service_or_initializes_account(monkeypatch):
    monkeypatch.delenv(worker.ENABLED,raising=False)
    with patch.object(worker,'configured',side_effect=AssertionError('No DB/market clients')):
        assert asyncio.run(worker.main(once=True))==0


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('kind',['SL','TP'])
def test_worker_uses_existing_engine_open_update_close_restart_and_duplicate(side,kind):
    async def scenario():
        market,now,store,svc=setup(side);logs=[]
        async def peek():return await store.load(now[0])
        store.peek=peek
        before=deepcopy(store.state)
        assert await worker.tick(svc,logs.append)  # OFF: heartbeat only.
        assert store.state['balance']==before['balance'] and store.state['mode']=='OFF'
        assert not any(e['kind']=='OPEN' for e in store.events)
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,store.revision)
        market.add();now[0]+=900;assert await worker.tick(svc,logs.append)
        market.add();now[0]+=900
        other=Service(store,market,svc.config,clock=lambda:now[0])
        assert all(await asyncio.gather(worker.tick(svc,logs.append),worker.tick(other,logs.append)))
        position=deepcopy(store.state['position']);assert position
        saved=deepcopy(store.state);await svc.close();await other.close()
        svc=Service(store,market,svc.config,clock=lambda:now[0]);assert (await svc.load())['state']==saved
        assert await worker.tick(svc,logs.append)
        market.signal=False;market.add(high='100.5',low='99.5');now[0]+=900;assert await worker.tick(svc,logs.append)
        assert store.state['position']
        tp=kind=='TP';long=side=='LONG'
        market.add(high='105' if long==tp else '101',low='95' if long!=tp else '99');now[0]+=900
        assert await worker.tick(svc,logs.append) and await worker.tick(svc,logs.append)
        opens=[e for e in store.events if e['kind']=='OPEN'];closes=[e['payload'] for e in store.events if e['kind']=='CLOSE']
        assert len(opens)==len(closes)==1
        assert closes[0]['exit_reason']==('TAKE_PROFIT' if tp else 'STOP_LOSS')
        from scripts.verify_auto42_execution import check_accounting
        check_accounting(position,closes[0],store.state)
        assert not (await svc.dashboard())['production_paper_verified']
        assert all(json.loads(line)['exchange_execution'] is False for line in logs)
        await svc.close()
    asyncio.run(scenario())


def test_worker_missing_account_refuses_initialization_and_database_or_market_errors_are_safe():
    async def scenario():
        market,now,store,svc=setup();logs=[]
        async def absent():return None
        store.peek=absent
        with patch.object(svc,'tick',side_effect=AssertionError('No implicit initialization')):
            assert not await worker.tick(svc,logs.append)
        async def peek():return await store.load(now[0])
        store.peek=peek;store.fail=True;before=deepcopy(store.state)
        assert not await worker.tick(svc,logs.append)
        assert store.state==before
        store.fail=False
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,store.revision)
        market.failure='NETWORK_ERROR';now[0]+=300
        assert not await worker.tick(svc,logs.append)
        assert store.state['mode']=='PAUSED' and store.state['position'] is None
        market.failure=None;now[0]+=300
        assert await worker.tick(svc,logs.append) and store.state['mode']=='ON'
        with patch.object(svc,'tick',side_effect=RuntimeError('DO_NOT_LOG_SECRET')):
            assert not await worker.tick(svc,logs.append)
        assert 'DO_NOT_LOG_SECRET' not in ''.join(logs)
        await svc.close()
    asyncio.run(scenario())


def test_serial_runner_waits_at_boundaries_skips_missed_intervals_and_closes_on_stop():
    async def scenario():
        stop=asyncio.Event();now=[121.0];calls=[];delays=[];closed=[]
        class Stub:
            async def close(self):closed.append(True)
        async def tick(*args):
            calls.append(now[0]);now[0]+=650  # Slow run; no catch-up burst.
            return True
        async def waiter(event,delay):
            delays.append(delay);now[0]+=delay
            if len(delays)==2:stop.set()
        with patch.object(worker,'tick',side_effect=tick):
            assert await worker.run(Stub(),stop,enabled=True,clock=lambda:now[0],waiter=waiter,emit=lambda _:None)==0
        assert calls==[121,1020] and delays==[249,250] and closed==[True]
    asyncio.run(scenario())


def test_shutdown_finishes_inflight_tick_and_starts_no_new_one():
    async def scenario():
        stop=asyncio.Event();events=[]
        class Stub:
            async def close(self):events.append('closed')
        async def tick(*args):
            events.append('inflight');stop.set();await asyncio.sleep(0)
            events.append('committed');return True
        with patch.object(worker,'tick',side_effect=tick):
            await worker.run(Stub(),stop,enabled=True,emit=lambda _:None)
        assert events==['inflight','committed','closed']
    asyncio.run(scenario())


def test_optional_blueprint_only_adds_disabled_worker_not_existing_web_service():
    from pathlib import Path
    text=Path('deploy/render-active43-worker.yaml').read_text()
    assert 'type: worker' in text and 'type: web' not in text
    assert 'autoDeployTrigger: "off"' in text and 'numInstances: 1' in text
    assert 'maxShutdownDelaySeconds: 90' in text
    assert 'startCommand: python -u -m scripts.active43_render_scheduler' in text
    assert 'key: AURA_ACTIVE43_BITGET_RENDER_SCHEDULER_ENABLED\n        value: "false"' in text
    assert 'AURA_AUTO42' not in text and 'PRACTICE' not in text


def test_recommended_cron_exits_each_run_is_disabled_and_uses_same_five_minute_schedule():
    from pathlib import Path
    text=Path('deploy/render-active43-cron.yaml').read_text()
    assert 'type: cron' in text and 'type: web' not in text
    assert 'schedule: "2-59/5 * * * *"' in text
    assert 'startCommand: python -u -m scripts.active43_render_scheduler --once' in text
    assert 'key: AURA_ACTIVE43_BITGET_RENDER_SCHEDULER_ENABLED\n        value: "false"' in text
    assert 'autoDeployTrigger: "off"' in text and 'maxShutdownDelaySeconds' not in text
