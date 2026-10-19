"""Offline regression fixtures; never production market or trade evidence."""
import asyncio
from copy import deepcopy
from decimal import Decimal as D
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI

from app.automated.api import router
from app.automated.engine import initial,advance,open_virtual,DemoError
from app.automated.service import Service
from app.automated.storage import SQLiteStore
from app.automated.strategy import strategy
from app.lab.models import digest
from tests.test_auto42 import fixture,bar


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('defect',['unrelated','missing','level','future','opposite','expired'])
def test_retest_requires_its_own_confirmed_original_break(side,defect):
    bars,snapshot,now=fixture(side);at=now[0]//900*900
    assert strategy(snapshot,bars,now[0])['direction']==side
    origin=snapshot['state']['retest_origin']
    if defect=='unrelated':origin['breakout_closed_at']=at-1800
    elif defect=='missing':snapshot['state'].pop('retest_origin')
    elif defect=='level':origin['level']='90'
    elif defect=='future':origin['breakout_closed_at']=at+900
    elif defect=='opposite':origin['direction']='SHORT' if side=='LONG' else 'LONG'
    elif defect=='expired':origin['breakout_closed_at']=at-9*900
    assert strategy(snapshot,bars,now[0])['reason']=='NO_CONFIRMED_STRUCTURE_BREAK'


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('mode',['ON','PAUSED','OFF','EMERGENCY'])
@pytest.mark.parametrize('exit_kind',['TP','SL'])
def test_extended_restart_catchup_protects_existing_position_without_historical_entries(side,mode,exit_kind):
    bars,_,now=fixture(side);at=now[0]//900*900
    state=initial(at,epoch='TEST_ONLY_CATCHUP');state['mode']='ON'
    plan=dict(direction=side,signal_at=at-900,stop_loss='98' if side=='LONG' else '102',take_profit='104' if side=='LONG' else '96',reason='TEST_ONLY',source='OFFLINE_FIXTURE')
    open_virtual(state,plan,bars[-1],at)
    state.update(mode=mode,watermark=at,last_bar_hash=digest(bars[-1].data()))
    if mode=='EMERGENCY':state['emergency']=True
    before=deepcopy(state['position'])
    for i in range(40):
        hit=i==4
        high='105' if hit and ((side=='LONG')==(exit_kind=='TP')) else '101'
        low='95' if hit and ((side=='SHORT')==(exit_kind=='TP')) else '99'
        bars.append(bar(at+i*900,high=high,low=low))
    end=at+40*900
    final,events=advance(state,bars,dict(direction=None,reason='NO_CONFIRMED_SETUP'),end+30)
    assert final['position'] is None and final['pending'] is None
    assert final['watermark']==end and final['missed_candles']==39
    assert final['mode']==mode
    assert not [e for e in events if e['kind']=='OPEN']
    closed=[e['payload'] for e in events if e['kind']=='CLOSE']
    assert len(closed)==1 and closed[0]['id']==before['id']
    assert closed[0]['exit_reason']==('TAKE_PROFIT' if exit_kind=='TP' else 'STOP_LOSS')
    again,new=advance(final,bars,dict(direction=None,reason='NO_CONFIRMED_SETUP'),end+30)
    assert again==final and new==[]
    # A missing candle or altered watermark still blocks, including protection.
    with pytest.raises(DemoError):advance(state,bars[:-6]+bars[-5:],dict(reason='WAIT'),end+30)


def test_extended_catchup_does_not_bypass_entry_guard():
    bars,_,now=fixture();at=now[0]//900*900
    state=initial(at);state.update(mode='ON',watermark=at,last_bar_hash=digest(bars[-1].data()))
    for i in range(33):bars.append(bar(at+i*900))
    with pytest.raises(DemoError,match='CATCHUP_LIMIT'):
        advance(state,bars,dict(direction='LONG',reason='TEST_ONLY'),at+33*900+30)


def test_closed_history_survives_heartbeat_flood_and_respects_epoch_cursor(tmp_path):
    async def run():
        store=SQLiteStore(tmp_path/'auto-paper-42.sqlite3');env=await store.load();state=env['state']
        from app.automated.engine import event
        for i in range(3):
            events=[event(state,'CLOSE',i,1000+i,dict(realized_pnl=str(i)))]
            env=await store.commit(env['revision'],state,events,events[0]['id'])
        for i in range(3):
            events=[event(state,'TICK',100+i*60+j,2000+i*60+j,{}) for j in range(60)]
            env=await store.commit(env['revision'],state,events,events[0]['id'])
        assert all(e['kind']=='TICK' for e in await store.history(limit=60))
        rows=await store.closed_trades(state['epoch'],limit=2)
        assert [e['payload']['realized_pnl'] for e in rows]==['2','1']
        assert len(await store.closed_trades(state['epoch'],before=rows[-1]['seq']))==1
        assert await store.closed_trades('other-epoch')==[]
        await store.close()
    asyncio.run(run())


def test_new_readers_require_owner_and_cannot_submit_commands():
    async def run():
        app=FastAPI();app.include_router(router)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='dummy-local-owner'):
                for path in ('/api/auto42/quote','/api/auto42/trades'):
                    assert (await client.get(path)).status_code==401
                    assert (await client.post(path,json={'direction':'LONG'})).status_code==405
    asyncio.run(run())


def test_authorized_quote_and_trade_reads_do_not_change_ledger(tmp_path):
    async def run():
        from tests.test_auto42 import DUMMY_OWNER
        class Quotes:
            calls=0
            async def get(self):
                self.calls+=1
                return dict(price='68000',time_ms=1800000000000,trade_id=1,source='OFFLINE_PUBLIC_QUOTE_FIXTURE')
            async def close(self):pass
        q=Quotes();store=SQLiteStore(tmp_path/'auto-paper-42.sqlite3')
        svc=Service(None,store,quotes=q);before=await store.load()
        app=FastAPI();app.include_router(router);app.state.auto42=svc
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD=DUMMY_OWNER):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',auth=('aura',DUMMY_OWNER)) as client:
                quote=await client.get('/api/auto42/quote')
                assert quote.status_code==200 and quote.json()['read_only'] and q.calls==1
                history=await client.get('/api/auto42/trades')
                assert history.status_code==200 and history.json()['trades']==[]
                assert (await client.get('/api/auto42/trades?limit=201')).status_code==422
                assert (await client.get('/api/auto42/trades?before=0')).status_code==422
        assert await store.load()==before and await store.history()==[]
        await svc.close()
    asyncio.run(run())


def test_missing_optional_history_rpc_does_not_hide_authoritative_portfolio(tmp_path):
    async def run():
        class Unmigrated(SQLiteStore):
            async def closed_trades(self,*args,**kwargs):raise DemoError('STORAGE_SCHEMA_MISSING')
        store=Unmigrated(tmp_path/'auto-paper-42.sqlite3');before=await store.load()
        svc=Service(None,store)
        view=await svc.dashboard()
        assert view['state']==before['state']
        assert view['history_is_partial'] and not view['history_available']
        assert view['history_error']=='STORAGE_SCHEMA_MISSING'
        assert await store.load()==before and await store.history()==[]
        await svc.close()
    asyncio.run(run())
