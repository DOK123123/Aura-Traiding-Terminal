import os
import pytest


def test_durable_signal_journal():
    if os.getenv('AURA_MANUAL_PAPER_VERIFY_POSTGRES')!='true':
        pytest.skip('explicit disposable PostgreSQL environment required')
    from scripts.verify_signal_lock_postgres import run
    assert run()['status']=='PASS'
