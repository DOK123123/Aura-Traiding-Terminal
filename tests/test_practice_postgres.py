"""Opt-in REAL PostgreSQL verification; never silently substitutes a mock."""
import os
import pytest
import scripts.verify_practice_postgres as verification
from scripts.verify_practice_postgres import run


def test_postgres_verifier_refuses_render_before_any_docker_call(tmp_path, monkeypatch):
    monkeypatch.setenv('RENDER', 'true')
    def forbidden(*args, **kwargs):
        pytest.fail('Docker must not be contacted from Render')
    monkeypatch.setattr(verification, 'docker', forbidden)
    with pytest.raises(ValueError, match='Render forbidden'):
        run(tmp_path / 'forbidden.json')


@pytest.mark.skipif(os.getenv('AURA_PRACTICE_VERIFY_POSTGRES') != 'true',
                    reason='NOT RUN: set AURA_PRACTICE_VERIFY_POSTGRES=true for disposable local Docker PostgreSQL')
def test_actual_postgresql_migration_execution_permissions_and_recovery(tmp_path):
    result = run(tmp_path / 'real-postgres-results.json')
    assert result['POSTGRESQL_VERIFIED'] and result['RLS_VERIFIED'] and result['OPEN_CLOSE_VERIFIED']
    assert all(c['status'] == 'PASS' for c in result['checks'])
    assert result['auto42_before_sha256'] == result['auto42_after_sha256']
    assert result['PRODUCTION_READY'] is False
