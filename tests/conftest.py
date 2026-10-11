"""Every application lifespan gets a disposable virtual ledger, never real state."""
import pytest


@pytest.fixture(autouse=True)
def isolate_paper_journal(tmp_path,monkeypatch):
    monkeypatch.setenv('PAPER_DB_PATH',str(tmp_path/'isolated-paper.sqlite3'))
