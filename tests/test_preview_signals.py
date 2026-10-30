"""Aura 5 integration: existing owner, no new account/service/execution authority."""
from unittest.mock import AsyncMock
import os

import pytest
from fastapi.testclient import TestClient

from app.manual_preview import main,signals
from app.manual_preview.config import parse
from app.manual_preview.page import page
from app.hunter.store import Store
from tests.test_hunter6 import bars,quote
from tests.test_manual_preview import preview,AUTH,environment


def test_preview_signal_flag_strict_and_default_off():
    env=environment();assert not parse(env).signals_enabled
    env['AURA_PREVIEW_SIGNALS_ENABLED']='true';assert parse(env).signals_enabled
    env['AURA_PREVIEW_SIGNALS_ENABLED']='yes'
    with pytest.raises(ValueError,match='PREVIEW_SIGNALS_FLAG_INVALID'):parse(env)


def test_integrated_page_replaces_old_panel_without_changing_legacy_default():
    body=page('DUMMY_TOKEN',server_signals=True)
    assert '/static/preview-signals.js' in body
    assert '/static/hunter6/hunter.js' in body
    assert '/static/signal-center.js' not in body and 'id="aura-notifications"' not in body
    assert 'Aura Live Manual Trader 5.0' in body and 'Aura 6' not in body
    assert '/static/signal-center.js' in page('DUMMY_TOKEN')
    assert 'id="aura-replay"' in body and 'id="manual-paper-panel"' in body


def test_preview_signals_reuse_owner_and_do_not_enable_manual(preview):
    path='/api/preview/signals/snapshot'
    assert preview.get(path).status_code==401
    assert preview.get(path,auth=('owner',AUTH[1])).status_code==401
    assert preview.get(path,auth=AUTH).status_code==503
    assert preview.post(path,auth=AUTH).status_code==403
    assert preview.get('/static/preview-signals.js').status_code==401
    assert preview.get('/static/preview-signals.js',auth=AUTH).status_code==200
    assert preview.get('/static/hunter6/hunter.js',auth=AUTH).status_code==200
    assert preview.app.state.manual_paper.store is None
    assert preview.get('/api/health').json()['signal_observer_enabled'] is False


@pytest.fixture
def integrated(tmp_path,monkeypatch):
    for key in list(os.environ):
        if key.startswith(('AURA_','SUPABASE_','BYBIT_','BINANCE_','BITGET_','CLOUDFLARE_','CF_')) or key in {'DATABASE_URL','PGPASSWORD','PGSERVICE','RENDER_API_KEY','RENDER_DEPLOY_HOOK','GITHUB_TOKEN','GH_TOKEN'}:
            monkeypatch.delenv(key)
    for key,value in {**environment(),'AURA_PREVIEW_SIGNALS_ENABLED':'true'}.items():monkeypatch.setenv(key,value)
    class ReadGuard:
        def verify_scope(self):return True
        def close(self):pass
    class PublicOnly:
        closed=False
        def __init__(self,client):self.client=client
        async def close(self):self.closed=True
        async def get(self,*args,**kwargs):return {'data':[]}
        async def snapshot(self,frame):
            if frame!='5m':raise ValueError('DUMMY_PUBLIC_FRAME_DOWN')
            return {'source':'BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2','frame':'5m','step':300,'bars':bars(320)[-260:],'quote':quote(96001.)}
    monkeypatch.setattr(main,'PreviewStore',lambda config:ReadGuard())
    monkeypatch.setattr(main,'_preview_probe_history',AsyncMock(return_value=None))
    monkeypatch.setattr(main,'_preview_probe_ws',AsyncMock(return_value=None))
    monkeypatch.setattr(signals,'PublicMarket',PublicOnly)
    monkeypatch.setattr(signals,'Store',lambda path:Store(tmp_path/'observations.sqlite'))
    monkeypatch.setattr(signals.time,'time',lambda:96001.)
    with TestClient(main.app) as client:yield client


def test_integrated_lifecycle_capture_auth_and_no_account_authority(integrated):
    c=integrated
    for _ in range(100):
        d=c.get('/api/preview/signals/snapshot',auth=AUTH).json()
        if d.get('observer',{}).get('cycles',0)>0:break
    assert d['observer']['running'] and d['observer']['cycles']>=1
    assert d['fresh_frames']==['5m'] and set(d['observer']['frame_errors'])=={'15m','1h','4h'}
    assert d['execution_enabled'] is False and d['account_connected'] is False
    assert d['storage']=='EPHEMERAL_RENDER_LOCAL' and c.app.state.manual_paper.store is None
    h=c.app.state.preview_signals
    assert h.registry=={'approved':[]}
    health=c.get('/api/health').json();assert health['signal_observer_enabled'] and health['signal_observer_running']
    assert '/static/preview-signals.js' in c.get('/',auth=AUTH).text
    path='/api/preview/signals/inputs?frame=5m'
    assert c.get(path).status_code==401
    assert len(c.get(path,auth=AUTH).json()['items'])==1
    assert c.get(path+'&limit=101',auth=AUTH).status_code==422
    assert c.post(path,auth=AUTH).status_code==403


def test_optional_observer_startup_failure_does_not_stop_existing_terminal(integrated,monkeypatch):
    # The same lifecycle helper must isolate optional storage failures.
    import asyncio
    from types import SimpleNamespace
    def unavailable(path):raise OSError('DUMMY_INTERNAL_DETAIL')
    monkeypatch.setattr(signals,'Store',unavailable)
    optional_app=SimpleNamespace(state=SimpleNamespace())
    async def run():
        async with signals.observer_lifespan(optional_app,None,True):
            assert optional_app.state.preview_signals is None
    asyncio.run(run())
    assert integrated.get('/',auth=AUTH).status_code==200
    assert integrated.get('/api/preview/signals/snapshot',auth=AUTH).status_code==200
