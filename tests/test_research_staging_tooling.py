"""Staging safeguards; no real trading/network credentials or paid resources."""
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from scripts.verify_research_staging import env_for,verify,process_usage
from scripts.staging.web_child import allowed


def test_staging_environment_does_not_inherit_secret_or_trading_configuration(tmp_path):
    with patch.dict('os.environ',AURA_AUTO42_SUPABASE_URL='DUMMY_FORBIDDEN',AURA_AUTO42_SUPABASE_SERVICE_KEY='DUMMY_FORBIDDEN',BYBIT_DEMO_API_KEY='DUMMY_FORBIDDEN',OPENAI_API_KEY='DUMMY_FORBIDDEN',AURA_RESEARCH_STATE_DIR='DUMMY_FORBIDDEN'):
        env=env_for(tmp_path/'checkout',8000,True,True)
    assert not any('SUPABASE' in k or 'API_KEY' in k or 'API_SECRET' in k for k in env)
    assert 'DUMMY_FORBIDDEN' not in env.values() and env['RENDER']=='true'
    assert env['AURA_AUTO42_SQLITE_PATH']=='' and env['AURA_RESEARCH_LLM_ENABLED']=='false'
    assert env['PAPER_DB_PATH']==str(tmp_path/'paper.sqlite3')
    assert env['LAB_DB_PATH']==str(tmp_path/'lab.sqlite3')
    assert env['AURA_STAGING_SANDBOX']==str(tmp_path)
    assert env_for(tmp_path/'checkout',8000,False)['AURA_AUTO42_SQLITE_PATH']==str(tmp_path/'auto-paper-42.sqlite3')


@pytest.mark.parametrize('host,expected',[('127.0.0.1',True),('::1',True),('localhost',True),('api.binance.com',False),('example.supabase.co',False),('169.254.169.254',False),('8.8.8.8',False)])
def test_network_allowlist_is_loopback_only(host,expected):assert allowed(host) is expected


def test_staging_tool_refuses_render_before_creating_resources(tmp_path):
    with patch.dict('os.environ',RENDER='true'),patch('tempfile.TemporaryDirectory',side_effect=AssertionError('MUST_NOT_CREATE')):
        with pytest.raises(AssertionError,match='LOCAL_ONLY_NOT_RENDER'):verify(tmp_path,tmp_path/'report.json')


def test_process_metrics_are_live_linux_measurements():
    result=process_usage(os.getpid())
    assert result['rss_mib']>0 and result['cpu_seconds']>=0


def test_git_snapshot_roundtrip_has_no_remote_or_trading_files(tmp_path):
    from scripts.verify_research_staging import git_snapshot_roundtrip
    approved=tmp_path/'checkout/docs/research-snapshot';approved.mkdir(parents=True)
    (approved/'index.json').write_text('{"DUMMY_PUBLIC_FIXTURE":true}')
    trading=tmp_path/'checkout/paper-sentinel';trading.write_text('DUMMY_UNCHANGED')
    result=git_snapshot_roundtrip(approved,tmp_path)
    assert result['hashes_equal'] and not result['remote_configured'] and not result['remote_publication']
    assert (approved/'index.json').read_text()=='{"DUMMY_PUBLIC_FIXTURE":true}'
    assert trading.read_text()=='DUMMY_UNCHANGED'
