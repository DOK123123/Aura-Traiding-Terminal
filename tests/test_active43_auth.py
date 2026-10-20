"""Scheduler authentication, no market, database, or execution calls."""
import asyncio,json
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from app.active43.api import router
from app.active43.service import Service,scheduler_auth_configuration

TOKEN='DUMMY_AUTH_SERVER_TOKEN_'+'x'*40
OTHER='DUMMY_AUTH_DIFFERENT_TOKEN_'+'y'*40
HEADER='X-Aura-Active43-Bitget-Token'


def test_precise_auth_rejections_and_runtime_rotation_without_cached_token(monkeypatch):
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',TOKEN)
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','DUMMY_OWNER_PASSWORD')
    async def run():
        service=Service(reason='ACTIVE43_DISABLED');app=FastAPI();app.include_router(router);app.state.active43=service
        async def read_only(scheduler_delivery=False):
            return dict(read_only=True,state_changed=False,paper_only=True,exchange_execution=False)
        with patch.object(service.diagnostics,'run',side_effect=read_only) as probe:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                path='/api/active43/diagnostics/scheduler'
                cases=[({},'SCHEDULER_TOKEN_MISSING'),({HEADER:OTHER},'SCHEDULER_TOKEN_MISMATCH'),
                    ({'X-Aura-Active43-Token':TOKEN},'SCHEDULER_TOKEN_MISSING'),
                    ({'X-Aura-Auto42-Token':TOKEN},'SCHEDULER_TOKEN_MISSING'),
                    ({HEADER:TOKEN,'Origin':'https://evil.invalid'},'SCHEDULER_ORIGIN_REJECTED'),
                    ({HEADER:TOKEN,'Sec-Fetch-Site':'cross-site'},'SCHEDULER_ORIGIN_REJECTED')]
                for headers,code in cases:
                    response=await c.post(path,headers=headers)
                    assert response.status_code==401 and response.json()['detail']['code']==code
                    assert response.json()['detail']['component']=='AURA43_SCHEDULER_AUTH'
                    assert TOKEN not in response.text and OTHER not in response.text
                    assert 'www-authenticate' not in response.headers
                response=await c.post(path,headers=[(HEADER,TOKEN),(HEADER,OTHER)])
                assert response.status_code==401 and response.json()['detail']['code']=='SCHEDULER_TOKEN_DUPLICATED'
                assert probe.call_count==0
                assert (await c.post(path,headers={HEADER:TOKEN})).status_code==200
                # Reuse same app/service: authentication reads current env every request.
                monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',OTHER)
                response=await c.post(path,headers={HEADER:TOKEN})
                assert response.status_code==401 and response.json()['detail']['code']=='SCHEDULER_TOKEN_MISMATCH'
                assert (await c.post(path,headers={HEADER:OTHER})).status_code==200
                assert probe.call_count==2
                monkeypatch.delenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET')
                response=await c.post(path,headers={HEADER:OTHER})
                assert response.status_code==503 and response.json()['detail']['code']=='SCHEDULER_NOT_CONFIGURED'
        await service.close()
    asyncio.run(run())


def test_owner_config_reports_names_and_booleans_not_values(monkeypatch):
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',' '+TOKEN+' ')
    monkeypatch.setenv('AURA_AUTO42_SCHEDULER_SECRET',' '+TOKEN+' ')
    value=scheduler_auth_configuration()
    assert value['token_present'] and value['token_has_outer_whitespace']
    assert not value['configured']
    assert value['conflicts_with_variables']==['AURA_AUTO42_SCHEDULER_SECRET']
    assert value['reads_environment_on_each_request']
    encoded=json.dumps(value)
    assert TOKEN not in encoded and 'sha256' not in encoded and 'length' not in encoded


def test_client_only_emits_whitelisted_structured_rejection_fields():
    import io,urllib.error
    from scripts.active43_scheduler import rejected_response
    body={'detail':{'code':'SCHEDULER_TOKEN_MISMATCH','component':'AURA43_SCHEDULER_AUTH',
        'header_received':True,'origin_rejected':False,'token':'NEVER_PRINT_THIS','header':'NEVER_PRINT_THIS'}}
    error=urllib.error.HTTPError('https://example.invalid',401,'ignored',{},io.BytesIO(json.dumps(body).encode()))
    evidence=rejected_response(error)
    assert 'SCHEDULER_TOKEN_MISMATCH' in evidence and '"header_received": true' in evidence
    assert 'NEVER_PRINT_THIS' not in evidence
