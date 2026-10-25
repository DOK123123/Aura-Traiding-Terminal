"""A START must not silently accept a different historical baseline."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch
import pytest
from app.automated.engine import DemoError
from tests.test_active43 import setup


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('tf',['5m','15m'])
@pytest.mark.parametrize('damage',['changed','missing'])
def test_start_cannot_bypass_history_and_explicit_off_rebaseline_is_required(side,tf,damage):
    async def run():
        m,n,store,svc=setup(side,tf=tf,name='SR_BOUNCE' if tf=='5m' else 'DONCHIAN')
        with patch('app.active43.service.scheduler_configured',return_value=True):
            await svc.control('START','a'*32,store.revision)
            original=m.bars[-1]
            if damage=='changed':m.bars[-1]=replace(original,volume=original.volume+Decimal(1))
            else:m.bars.pop()
            m.bars.append(replace(original,time=original.time+m.step));n[0]+=m.step
            await svc.tick()
            assert store.state['mode']=='PAUSED'
            await svc.control('STOP','b'*32)
            before=deepcopy((store.state,store.events,store.revision))
            with pytest.raises(DemoError,match='HISTORY_CANDLE_CHANGED' if damage=='changed' else 'HISTORY_CANDLE_MISSING'):
                await svc.control('START','c'*32,store.revision)
            assert (store.state,store.events,store.revision)==before
            assert store.state['balance']=='10000' and store.state['mode']=='OFF'
            # Recovery means restoring the original candle, never blessing a new hash.
            m.bars=[b for b in m.bars if b.time!=original.time]+[original]
            m.bars.sort(key=lambda b:b.time)
            await svc.control('START','d'*32,store.revision)
            assert store.state['mode']=='ON' and store.state['balance']=='10000'
            restarted=deepcopy((store.state,store.events,store.revision))
            duplicate=await svc.control('START','d'*32,store.revision)
            assert duplicate['duplicate'] and (store.state,store.events,store.revision)==restarted
        await svc.close()
    asyncio.run(run())
