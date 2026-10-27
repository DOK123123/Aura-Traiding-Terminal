from dataclasses import asdict,replace
from decimal import Decimal as D
import json
from pathlib import Path
import pytest
from research.manual_analyst_replay.config import Config
from research.manual_analyst_replay.protocol import splits
from research.manual_analyst_replay.__main__ import run,analyst_hash
from research.manual_analyst_replay.dataset import sha256
from tests.test_manual_replay_data import make_file
from tests.test_manual_replay_engine import T,bar,signal,cfg
from research.manual_analyst_replay.execution import execute


def protocol(tmp_path):
    p=dict(version=1,start=T,end=T+480*60,frozen_at=T-86400,splits=[60,20,20],exposure_registry_complete=False,
           prior_exposure=[],config=asdict(Config()),analyst_code_hash=analyst_hash())
    path=tmp_path/'protocol.json';path.write_text(json.dumps(p));return path


def test_cli_reproducible_artifacts_no_network_or_existing_output_changes(tmp_path):
    manifest=make_file(tmp_path);p=protocol(tmp_path);out=tmp_path/'result'
    summary=run(manifest,p,out)
    assert len(summary['runs'])==9 and summary['verdict']=='INSUFFICIENT_EVIDENCE'
    assert all(r['metrics']['trades']==0 and r['metrics']['profit_factor'] is None for r in summary['runs'].values())
    assert all(s['independence']=='NOT_INDEPENDENT' for s in summary['splits'])
    hashes=json.loads((out/'artifact_hashes.json').read_text())
    assert all(sha256(out/name)==h for name,h in hashes.items())
    before={f.name:sha256(f) for f in out.iterdir()}
    with pytest.raises(ValueError,match='OUTPUT_ALREADY_EXISTS'):run(manifest,p,out)
    assert {f.name:sha256(f) for f in out.iterdir()}==before
    run(manifest,p,tmp_path/'rerun')
    assert (tmp_path/'rerun'/'summary.json').read_bytes()==(out/'summary.json').read_bytes()


def test_no_render_or_changed_analyst_code_allowed(tmp_path,monkeypatch):
    m=make_file(tmp_path);p=protocol(tmp_path)
    monkeypatch.setenv('RENDER','true')
    with pytest.raises(ValueError,match='OFFLINE_ONLY'):run(m,p,tmp_path/'blocked')
    monkeypatch.delenv('RENDER')
    data=json.loads(p.read_text());data['analyst_code_hash']='0'*64;p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='ANALYST_SOURCE_CHANGED'):run(m,p,tmp_path/'changed')
    assert not (tmp_path/'changed').exists()


def test_previous_calendar_and_unknown_registry_cannot_be_new_oos(tmp_path):
    p=json.loads(protocol(tmp_path).read_text());m={'availability_mode':'OBSERVED','data_kind':'REAL_PUBLIC_ARCHIVE'}
    p['exposure_registry_complete']=True;p['prior_exposure']=[{'start':T,'end':T+480*60,'study':'other_exchange_already_seen'}]
    result=splits(p,m)
    assert result[-1]['independence']=='NOT_INDEPENDENT' and 'PREVIOUSLY_VIEWED_CALENDAR' in result[-1]['reasons']
    p['prior_exposure']=[];p['frozen_at']=T+480*60
    assert 'CONFIG_FROZEN_AFTER_PERIOD_STARTED' in splits(p,m)[-1]['reasons']


def test_no_network_execution_or_web_imports_in_research_module():
    import ast
    root=Path('research/manual_analyst_replay')
    allowed={'app.models','app.aura_trader5_scenarios','app.lab.execution','app.lab.models'}
    for file in root.glob('*.py'):
        tree=ast.parse(file.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                assert not any(i.name.split('.')[0] in {'httpx','requests','socket','subprocess','fastapi','ccxt'} for i in node.names)
            if isinstance(node,ast.ImportFrom) and node.module and node.module.startswith('app.'):
                assert node.module in allowed
    assert 'manual_analyst_replay' not in Path('app/main.py').read_text()


def test_remaining_daily_budget_and_zero_funding_are_explicit():
    r=execute([bar()],60,[signal()],cfg(daily_loss_pct='0.01'))
    assert D(r['trades'][0]['risk_usdt'])<=1
    assert r['funding']=='NOT_INCLUDED'


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_original_analyst_to_execution_to_pnl_end_to_end(side):
    from tests.test_aura_trader5_scenarios import windows,NOW
    from app.aura_trader5_scenarios import assess
    from research.manual_analyst_replay.adapter import Signal
    from research.manual_analyst_replay.dataset import Bar
    r=assess(windows(side),NOW);assert r['state']==side
    p=r['scenario'];at=NOW//60*60+60
    s=Signal(('a' if side=='LONG' else 'b')*64,NOW//300*300,NOW,r['valid_until'],side,
        D(str(p['entry_zone']['low'])),D(str(p['entry_zone']['high'])),D(str(p['stop_loss'])),D(str(p['take_profit'])))
    # Synthetic raw entry safely inside the unchanged scenario's zone after costs.
    entry=(s.low+s.high)/2;target=s.target
    first=Bar(at,entry,entry+D('.1'),entry-D('.1'),entry,D(100),at+62)
    second=Bar(at+60,entry,max(entry,target)+D(1),min(entry,target)-D(1),target,D(100),at+122)
    result=execute([first,second],60,[s],Config())
    assert len(result['trades'])==1,result['rejections']
    assert result['trades'][0]['direction']==side and result['trades'][0]['exit_reason']=='TAKE_PROFIT'
    assert D(result['metrics']['final_balance'])==10000+D(result['trades'][0]['realized_pnl'])
