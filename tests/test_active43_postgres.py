import os
import pytest
from scripts import verify_active43_postgres as verifier

def test_postgres_cli_refuses_render_before_docker(tmp_path,monkeypatch):
    monkeypatch.setenv('RENDER','true')
    def forbidden(*a,**kw):raise AssertionError('No Docker in Render')
    monkeypatch.setattr(verifier,'docker',forbidden)
    with pytest.raises(ValueError):verifier.run(tmp_path/'none.json')

@pytest.mark.skipif(os.getenv('AURA_ACTIVE43_VERIFY_POSTGRES')!='true',reason='Explicit local PostgreSQL opt-in required')
def test_actual_sql_transactions_roles_recovery_and_cycles(tmp_path,monkeypatch):
    monkeypatch.delenv('RENDER',raising=False)
    report=verifier.run(tmp_path/'active43.json')
    assert report['POSTGRESQL_VERIFIED'] and report['RLS_VERIFIED']
    assert report['preparation']['owner_readiness_get_byte_identical_sql']
    assert report['cloudflare_off_cycles']['distinct_saved_slots']==2
    assert report['cloudflare_off_cycles']['duplicate_without_write']
    assert report['cloudflare_off_cycles']['paper_state_unchanged']
    assert len(report['cases'])==7 and len(report['checks'])>=8
    assert not report['PRODUCTION_PAPER_VERIFIED']
    assert len(report['render_cycles'])==2
    assert all(c['actual_render_scheduler'] and not c['external_scheduler_http'] and c['no_browser'] and c['restart_restored'] for c in report['render_cycles'])
    assert all(c['actual_scheduler_cli'] and c['external_scheduler_http'] and c['no_browser'] for c in report['native_cycles'])


def test_browser_cli_refuses_render_even_child_before_server(monkeypatch):
    import runpy
    monkeypatch.setenv('RENDER','true')
    monkeypatch.setattr('sys.argv',['verify_active43_browser','--child','8000'])
    with pytest.raises(ValueError,match='LOCAL_OFFLINE_ONLY'):
        runpy.run_module('scripts.verify_active43_browser',run_name='__main__')


def test_cloudflare_sql_harness_refuses_render_before_local_http(monkeypatch):
    import asyncio
    monkeypatch.setenv('RENDER','true')
    with pytest.raises(ValueError,match='LOCAL_OFFLINE_ONLY'):
        asyncio.run(verifier.cloudflare_off_cycles(None))
