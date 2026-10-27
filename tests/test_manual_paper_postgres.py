import os
import pytest
from scripts.verify_manual_paper_postgres import run


def test_manual_postgres_harness_refuses_production(monkeypatch):
    monkeypatch.setenv('RENDER','true')
    with pytest.raises(ValueError,match='LOCAL_DISPOSABLE_ONLY'):run()


@pytest.mark.skipif(os.getenv('AURA_MANUAL_PAPER_VERIFY_POSTGRES')!='true',reason='Disposable Docker PostgreSQL opt-in required')
def test_real_postgres_manual_transactions_roles_and_restart(monkeypatch):
    monkeypatch.delenv('RENDER',raising=False)
    result=run()
    assert result['POSTGRESQL_VERIFIED'] and result['RLS_VERIFIED']
    assert len(result['checks'])==10 and result['production_writes'] is False
