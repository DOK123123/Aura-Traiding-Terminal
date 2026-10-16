"""BACKTESTER: frozen configurations; reused Lab engine, fresh ledger per split."""
import hashlib
from pathlib import Path
import time
from app.lab.models import digest,LabError
from app.automated.engine import POLICY
from scripts.research_lab_v2 import replay
from .registry import PROTOCOL,HYPOTHESES
from .strategies import HypothesisDecisions
from .auditor import audit_run,conclusion

ROOT=Path(__file__).resolve().parents[2]
FILES=('app/research/registry.py','app/research/strategies.py','app/research/experiment.py','app/research/auditor.py',
 'app/research/data.py','app/lab/v2_execution.py','app/lab/v2_strategies.py','app/lab/indicators.py','app/lab/models.py',
 'app/lab/series.py','app/automated/engine.py','app/automated/strategy.py','app/indicators.py','scripts/research_lab_v2.py',
 'scripts/research_candidates.py','scripts/research_aura43_profiles.py','scripts/audit_lab_v2_accounting.py','docs/RESEARCH_CYCLE_PROTOCOL.json')

def code_hashes() -> dict:return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}

def frozen_config(name:str,source:dict) -> dict:
    if name not in HYPOTHESES:raise LabError('INVALID_HYPOTHESIS')
    return dict(hypothesis=name,hypothesis_spec=HYPOTHESES[name],protocol=PROTOCOL,policy=POLICY,
        source_sha256=source['sha256'],code_hashes=code_hashes(),llm_can_change_parameters=False)


def execute(config:dict,bars,source:dict) -> dict:
    if not __debug__:raise LabError('AUDIT_REQUIRES_ASSERTIONS')
    if digest(config)!=digest(frozen_config(config['hypothesis'],source)):raise LabError('SOFTWARE_MISMATCH')
    start=PROTOCOL['start'];end=PROTOCOL['end_exclusive'];n=(end-start)//900
    a=start+n*60//100*900;b=start+n*80//100*900
    ranges=(('train',start,a),('validation',a,b),('test',b,end))
    data=HypothesisDecisions(bars);runs=[];audits=[];deadline=time.monotonic()+180
    # No parameter search or selection. Sensitivity never touches the final test.
    for label,lo,hi in ranges:
        for scale in (PROTOCOL['sensitivity_scales'] if label!='test' else ['1']):
            if time.monotonic()>deadline:raise LabError('COMPUTE_TIMEOUT')
            run=replay(bars,data.rows(config['hypothesis'],lo,hi,scale),lo,hi,'AI_'+config['hypothesis'],label)
            run['scale']=scale;audits.append(dict(split=label,scale=scale,**audit_run(run,bars)));runs.append(run)
    # Prefix invariance checked at each split boundary; no access to future data.
    proof=[]
    for cutoff in (a,b):
        index=next(i for i,x in enumerate(bars) if x.time+900==cutoff)
        prefix=HypothesisDecisions(bars[:index+1])
        if data.decision(index,config['hypothesis'])!=prefix.decision(index,config['hypothesis']):raise LabError('CAUSALITY_FAILURE')
        proof.append(cutoff)
    result=dict(version=PROTOCOL['version'],research_only=True,activation_available=False,config=config,config_hash=digest(config),
        source=source,splits=[dict(name=label,start=lo,end_exclusive=hi,fresh_ledger=True) for label,lo,hi in ranges],
        runs=runs,audits=audits,causal_prefix_checks=proof,auditor=conclusion(runs),
        llm_used=False,role_methods=dict(RESEARCHER='CURATED_FROZEN_PROTOCOL_NOT_LLM',BACKTESTER='EXISTING_LAB_V2_REPLAY',AUDITOR='INDEPENDENT_DETERMINISTIC_CHECKS'),
        final_test_is_independent=False,limitations=PROTOCOL['limitations'])
    result['checksum']=digest(result);return result
