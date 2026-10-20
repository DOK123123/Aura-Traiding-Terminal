"""Owner shutdown/restart versus ordinary scheduler: isolated fixtures only."""
import asyncio
from copy import deepcopy
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI

from app.active43.api import router
from app.active43.service import Service
from tests.test_active43 import setup


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('action',['STOP','EMERGENCY'])
@pytest.mark.parametrize('phase',['pending','open'])
def test_shutdown_persists_across_restart_blocks_entries_and_keeps_protective_exits(side,action,phase):
    async def scenario():
        market,now,store,svc=setup(side)
        with patch('app.active43.service.scheduler_configured',return_value=True):
            await svc.control('START','a'*32,1)
        market.add();now[0]+=900;await svc.tick()
        assert store.state['pending'] and not store.state['position']
        if phase=='open':
            market.add();now[0]+=900;await svc.tick()
            assert store.state['position']
        token='DUMMY_AUTONOMY_SCHEDULER_'+'x'*40;password='DUMMY_AUTONOMY_OWNER'
        app=FastAPI();app.include_router(router);app.state.active43=svc
        with patch.dict('os.environ',AURA_ACTIVE43_BITGET_SCHEDULER_SECRET=token,AURA_TESTNET_VIEW_PASSWORD=password):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                body={'action':action,'request_id':'b'*32}
                assert (await client.post('/api/active43/control',json=body)).status_code==401
                response=await client.post('/api/active43/control',json=body,auth=('aura',password),headers={'X-Aura-Paper':'local-only'})
                assert response.status_code==200 and response.json()['state_saved']
                repeated=await client.post('/api/active43/control',json=body,auth=('aura',password),headers={'X-Aura-Paper':'local-only'})
                assert repeated.json()['duplicate']
                saved=deepcopy(store.state)
                assert saved['pending'] is None and not saved['data_recovery_armed']
                await svc.close();svc=Service(store,market,svc.config,clock=lambda:now[0]);app.state.active43=svc
                assert (await svc.load())['state']==saved
                market.add(high='105',low='95');now[0]+=900
                headers={'X-Aura-Active43-Bitget-Token':token}
                other=Service(store,market,svc.config,clock=lambda:now[0])
                response,_=await asyncio.gather(client.post('/api/active43/tick',headers=headers),other.tick())
                assert response.status_code==200 and response.json()['state_saved']
                assert response.json()['exchange_execution'] is False
                assert (await client.post('/api/active43/tick',headers=headers)).json()['duplicate']
                assert store.state['mode']==('OFF' if action=='STOP' else 'EMERGENCY')
                assert store.state['position'] is None and store.state['pending'] is None
                assert len([e for e in store.events if e['kind']=='OPEN'])==(1 if phase=='open' else 0)
                assert len([e for e in store.events if e['kind']=='CLOSE'])==(1 if phase=='open' else 0)
                assert not (await svc.dashboard())['production_paper_verified']
                await other.close();await svc.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_owner_stop_cancels_outage_recovery_permission_after_restart(side):
    async def scenario():
        market,now,store,svc=setup(side)
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        market.failure='MARKET_UNAVAILABLE';now[0]+=300;await svc.tick()
        assert store.state['mode']=='PAUSED' and store.state['data_recovery_armed']
        await svc.control('STOP','b'*32)
        saved=deepcopy(store.state);await svc.close()
        svc=Service(store,market,svc.config,clock=lambda:now[0])
        assert (await svc.load())['state']==saved
        market.failure=None;market.add();now[0]=market.bars[-1].time+900+30
        await svc.tick()
        assert store.state['mode']=='OFF' and not store.state['data_recovery_armed']
        assert store.state['position'] is None and not any(e['kind']=='OPEN' for e in store.events)
        await svc.close()
    asyncio.run(scenario())
