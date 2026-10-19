"""Explicit opt-in for disposable real PostgreSQL; never production Supabase."""
import os

import pytest

from scripts import verify_auto42_postgres as verification


def test_postgres_verifier_refuses_render_without_docker(tmp_path,monkeypatch):
    monkeypatch.setenv('RENDER','true')
    def forbidden(*args,**kwargs):raise AssertionError('Docker must not be invoked')
    monkeypatch.setattr(verification,'docker',forbidden)
    with pytest.raises(ValueError,match='Local verification only'):
        verification.run(tmp_path/'not-written.json')


def test_postgres_verifier_requires_history_and_cutoff_together(tmp_path,monkeypatch):
    monkeypatch.delenv('RENDER',raising=False)
    def forbidden(*args,**kwargs):raise AssertionError('Docker must not be invoked')
    monkeypatch.setattr(verification,'docker',forbidden)
    with pytest.raises(ValueError,match='required together'):
        verification.run(tmp_path/'not-written.json',signal_at=900)


@pytest.mark.skipif(os.getenv('AURA_AUTO42_VERIFY_POSTGRES')!='true',reason='Explicit disposable PostgreSQL opt-in required')
def test_real_postgres_automatic_cycles_and_failure_recovery(tmp_path,monkeypatch):
    monkeypatch.delenv('RENDER',raising=False)
    report=verification.run(tmp_path/'auto42-postgres.json')
    assert report['POSTGRESQL_VERIFIED'] and report['RLS_VERIFIED']
    assert len(report['cases'])==6 and len(report['checks'])==8
    assert report['TECHNICAL_EXECUTION']=='PASS' and not report['PRODUCTION_VERIFIED']
