"""Bounded read-only summary of bundled manual experiments; no computation."""
import json
from pathlib import Path
from app.lab.models import digest,LabError
ROOT=Path(__file__).resolve().parents[2]

def summary() -> dict|None:
    p=ROOT/'docs/AI_RESEARCH_V1/summary.json'
    if not p.exists():return None
    with p.open('rb') as f:raw=f.read(128*1024+1)
    if len(raw)>128*1024:raise LabError('RESEARCH_INTEGRITY')
    result=json.loads(raw);checksum=result.pop('checksum',None)
    if checksum!=digest(result) or result.get('candidate_for_paper_enabled') is not False or result.get('independent_test_available') is not False:raise LabError('RESEARCH_INTEGRITY')
    result['checksum']=checksum;return result
