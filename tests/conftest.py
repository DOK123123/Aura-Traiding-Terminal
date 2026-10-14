"""Every application lifespan gets a disposable virtual ledger, never real state."""
import pytest


@pytest.fixture(autouse=True)
def isolate_paper_journal(tmp_path,monkeypatch):
    monkeypatch.setenv('PAPER_DB_PATH',str(tmp_path/'isolated-paper.sqlite3'))


@pytest.fixture(autouse=True)
def isolate_forward_configuration(monkeypatch):
    for name in ('AURA_FORWARD_SQLITE_PATH','AURA_FORWARD_SUPABASE_URL',
                 'AURA_FORWARD_SUPABASE_SERVICE_KEY','AURA_FORWARD_SCHEDULER_SECRET'):
        monkeypatch.delenv(name,raising=False)
