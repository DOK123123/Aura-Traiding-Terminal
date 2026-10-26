"""Read-only runtime probes must neither seed state nor disclose environment secrets."""
import asyncio
import json
import os
from unittest.mock import AsyncMock,patch

from app.manual_paper.commands import ManualCommands
from app.manual_paper.store import ManualStore
from scripts.manual_paper_preflight import storage_check,preflight


def config(tmp_path):
    return dict(AURA_MANUAL_PAPER_ENABLED='true',AURA_MANUAL_PAPER_STORAGE='persistent-disk',
                AURA_MANUAL_PAPER_MOUNT=str(tmp_path),AURA_MANUAL_PAPER_DB=str(tmp_path/'manual-paper.sqlite3'),
                AURA_TESTNET_VIEW_PASSWORD='DUMMY_ONLY_OWNER_SECRET',AURA_ACTIVE43_SECRET='DUMMY_ONLY_DO_NOT_READ')


def test_unconfigured_probe_never_creates_a_file_or_prints_secrets(tmp_path):
    env=config(tmp_path)
    report=storage_check(env)
    assert not report['ready']
    assert not (tmp_path/'manual-paper.sqlite3').exists()
    assert 'DUMMY_ONLY' not in json.dumps(report)


def test_configured_probe_has_no_account_seed_side_effect(tmp_path,monkeypatch):
    monkeypatch.setattr(os.path,'ismount',lambda p:p==tmp_path)
    report=storage_check(config(tmp_path))
    assert report['ready'] and report['code']=='READY_EMPTY_DATABASE_NOT_INITIALIZED'
    assert not (tmp_path/'manual-paper.sqlite3').exists()


def test_existing_ledger_is_read_only_and_fresh_quote_checked(tmp_path,monkeypatch):
    monkeypatch.setattr(os.path,'ismount',lambda p:p==tmp_path)
    env=config(tmp_path);store=ManualStore(env['AURA_MANUAL_PAPER_DB'])
    ManualCommands(store).open('a'*32,'LONG','0.01','79500','81000',dict(source='Bitget USDT-M Futures',time=1793007900000,price='80000'))
    before=store.path.read_bytes()
    with patch('scripts.manual_paper_preflight.fetch_execution_quote',new=AsyncMock(return_value=dict(
            source='Bitget USDT-M Futures',symbol='BTCUSDT',product='USDT-FUTURES',time=1793007900000))):
        report=asyncio.run(preflight(client=object(),env=env))
    assert report['launch_ready'] and report['journal_read_verified']
    assert report['version']==1 and store.path.read_bytes()==before
    assert store.load()[0].position.id=='a'*32
    assert 'DUMMY_ONLY' not in json.dumps(report)


def test_probe_market_failure_does_not_hide_storage_state(tmp_path,monkeypatch):
    monkeypatch.setattr(os.path,'ismount',lambda p:p==tmp_path)
    with patch('scripts.manual_paper_preflight.fetch_execution_quote',new=AsyncMock(side_effect=ValueError('DUMMY_ONLY_NOT_FOR_LOGS'))):
        report=asyncio.run(preflight(client=object(),env=config(tmp_path)))
    assert report['ready'] and not report['launch_ready']
    assert report['market']['code']=='BITGET_QUOTE_UNAVAILABLE'
    assert 'DUMMY_ONLY' not in json.dumps(report)


def test_nonexistent_directory_and_read_only_path_not_ready(tmp_path,monkeypatch):
    monkeypatch.setattr(os.path,'ismount',lambda p:p==tmp_path)
    env=config(tmp_path)
    env['AURA_MANUAL_PAPER_DB']=str(tmp_path/'missing'/'manual-paper.sqlite3')
    assert not storage_check(env)['ready']
    monkeypatch.setattr(os,'access',lambda *a:False)
    assert not storage_check(config(tmp_path))['ready']


def test_probe_refuses_foreign_database_before_reading_portfolio(tmp_path,monkeypatch):
    import sqlite3
    monkeypatch.setattr(os.path,'ismount',lambda p:p==tmp_path)
    env=config(tmp_path)
    with sqlite3.connect(env['AURA_MANUAL_PAPER_DB']) as db:
        db.execute('CREATE TABLE active43(dummy TEXT)')
        db.execute("INSERT INTO active43 VALUES('DUMMY_ONLY_MUST_NOT_READ')")
    report=storage_check(env)
    assert not report['ready'] and report['code']=='JOURNAL_READ_FAILED'
    assert 'DUMMY_ONLY' not in json.dumps(report)
