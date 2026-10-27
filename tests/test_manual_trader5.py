"""Unified planner API: real disposable ledger, mocked public market only."""
import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from tests.test_manual_paper_integration import setup, quote, post, BODY, AUTH, HEAD, STAMP


def preview(client,body=None,**kwargs):
    return client.post('/api/manual-paper/preview',json=body or BODY,auth=AUTH,headers=HEAD,**kwargs)


@pytest.mark.parametrize('side,stop,target,risk,reward',[
    ('LONG','79500','81000','5.967006','9.023994'),
    ('SHORT','80500','79000','5.963','9.046'),
])
def test_preview_exact_costs_and_never_seeds_or_writes(setup,side,stop,target,risk,reward):
    c,s=setup
    r=preview(c,{**BODY,'side':side,'stop':stop,'target':target})
    assert r.status_code==200,r.text
    p=r.json()
    assert Decimal(p['risk'])==Decimal(risk)
    assert Decimal(p['net_reward'])==Decimal(reward)
    assert Decimal(p['net_rr'])==Decimal(reward)/Decimal(risk)
    assert p['read_only'] and p['virtual_only'] and p['real_money_execution']=='DISABLED'
    assert s.store.load()==(None,0)
    assert s.store.lookup(BODY['request_id'],'OPEN',{}) is None


def test_preview_auth_and_csrf_and_invalid_inputs(setup):
    c,s=setup
    assert c.post('/api/manual-paper/preview',json=BODY).status_code==401
    assert c.post('/api/manual-paper/preview',json=BODY,auth=AUTH).status_code==403
    for mutation in [{'quantity':'1'},{'stop':'90000'},{'quantity':'0'},{'entry_limit':'1'}]:
        assert preview(c,{**BODY,**mutation}).status_code==409
    assert s.store.load()==(None,0)


def test_preview_existing_position_never_changes_account(setup):
    c,s=setup;post(c);before=s.store.load()
    assert preview(c).json()['code']=='POSITION_ALREADY_OPEN'
    after=s.store.load()
    assert after[1]==before[1] and after[0].position==before[0].position
    assert after[0].balance==before[0].balance


@pytest.mark.parametrize('side,limit,code',[
    ('LONG','80000','ENTRY_PRICE_MOVED'),('SHORT','80001','ENTRY_PRICE_MOVED'),
])
def test_adverse_price_bounds_apply_transactionally(setup,side,limit,code):
    c,s=setup
    body={**BODY,'side':side,'stop':'79500' if side=='LONG' else '80500',
          'target':'81000' if side=='LONG' else '79000','entry_limit':limit}
    assert preview(c,body).json()['code']==code
    assert post(c,body=body).json()['code']==code
    assert s.store.load()==(None,0)


def attach(c,s,*,expires=60,state='LONG'):
    now=STAMP/1000
    snapshot=dict(state=state,generated_at=now,valid_until=now+expires,asof_closed_at=int(now)//300*300,
                  scenario=dict(stop_loss=79500,take_profit=81000,entry_zone=dict(low=79990,high=80010)))
    c.app.state.aura_analyst=SimpleNamespace(inspect=AsyncMock(return_value=snapshot))
    return snapshot,{**BODY,'entry_limit':'80001','analyst_at':now}


@pytest.mark.parametrize('mutation,code',[
    (lambda p:p.update(state='WAIT',scenario=None),'STALE_ANALYST'),
    (lambda p:p.update(valid_until=STAMP/1000),'STALE_ANALYST'),
    (lambda p:p.update(generated_at=STAMP/1000-1),'STALE_ANALYST'),
    (lambda p:p.update(asof_closed_at=0),'STALE_ANALYST'),
    (lambda p:p['scenario'].update(stop_loss=79000),'ANALYST_PLAN_CHANGED'),
    (lambda p:p['scenario'].update(entry_zone=dict(low=79000,high=79500)),'ENTRY_OUTSIDE_ZONE'),
])
def test_stale_wait_revised_or_outside_zone_never_opens(setup,mutation,code):
    c,s=setup;snapshot,body=attach(c,s);mutation(snapshot)
    assert preview(c,body).json()['code']==code
    assert post(c,body=body).json()['code']==code
    assert s.store.load()==(None,0)


def test_copied_signal_retry_after_expiry_and_quote_failure_returns_receipt(setup):
    c,s=setup;signal,body=attach(c,s)
    assert preview(c,body).status_code==200
    first=post(c,body=body);assert first.status_code==200,first.text
    signal.update(state='WAIT',scenario=None)
    s.quote.side_effect=ValueError('MARKET_UNAVAILABLE')
    assert post(c,body=body).json()==first.json()
    assert s.store.load()[1]==1
    assert post(c,body={**body,'analyst_at':body['analyst_at']-1}).json()['code']=='IDEMPOTENCY_CONFLICT'


def test_deadline_rechecked_inside_sqlite_lock_and_passed_to_postgres_store(setup):
    c,s=setup;_,body=attach(c,s,expires=1)
    original=s.store.execute;observed=[]
    def delayed(*a,**kw):
        observed.append(kw['quote_ms'])
        s.clock=lambda:STAMP/1000+1.1
        return original(*a,**kw)
    s.store.execute=delayed
    assert post(c,body=body).json()['code']=='STALE_ANALYST'
    assert observed==[STAMP-4000]
    assert s.store.load()==(None,0)


def test_self_directed_plan_works_during_analyst_wait(setup):
    c,s=setup;attach(c,s,state='WAIT')
    assert post(c,body={**BODY,'entry_limit':'80001'}).status_code==200
    assert not c.app.state.aura_analyst.inspect.await_count


def test_lifespan_closes_all_services_even_when_manual_cleanup_fails(monkeypatch):
    from fastapi import FastAPI
    from app import main
    active=SimpleNamespace(close=AsyncMock())
    analyst=SimpleNamespace(close=AsyncMock())
    manual=SimpleNamespace(store=None,close=AsyncMock(side_effect=RuntimeError('DUMMY_CLOSE_FAILURE')))
    monkeypatch.setattr(main,'configured_active43',lambda:active)
    monkeypatch.setattr(main,'AnalystService',lambda:analyst)
    monkeypatch.setattr(main,'configured_manual_paper',lambda c:manual)
    async def run():
        with pytest.raises(RuntimeError,match='DUMMY_CLOSE_FAILURE'):
            async with main.lifespan(FastAPI()):pass
    asyncio.run(run())
    active.close.assert_awaited_once();analyst.close.assert_awaited_once()
