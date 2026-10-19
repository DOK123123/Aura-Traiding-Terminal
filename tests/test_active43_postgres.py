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
    assert len(report['cases'])==7 and len(report['checks'])>=8
    assert not report['PRODUCTION_PAPER_VERIFIED']
