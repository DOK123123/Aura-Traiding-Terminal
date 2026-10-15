"""Owner-only immutable offline evidence. Never touches a portfolio or runs tests."""
import asyncio
import hashlib
import json
from pathlib import Path
from fastapi import APIRouter,Depends
from fastapi.responses import JSONResponse
from app.paper.api import owner,HEADERS
from app.lab.models import digest

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'docs/AURA_AUTO42_EXECUTION_VERIFICATION.json'
ALLOWED={'PASS','FAIL','NOT_TESTED','INCONCLUSIVE'}
router=APIRouter(prefix='/api/auto42-verification',tags=['Isolated paper execution evidence'])

def evidence():
    empty=dict(isolated=dict(status='NOT_TESTED'),historical=dict(status='NOT_TESTED'),
               live=dict(status='NOT_TESTED',reason='DEPLOYED_OPEN_CLOSE_NOT_OBSERVED'),
               read_only=True,test_only=True,live_execution_enabled=False)
    try:
        if REPORT.stat().st_size>512*1024:raise ValueError()
        value=json.loads(REPORT.read_bytes());checksum=value.pop('checksum')
        if digest(value)!=checksum:raise ValueError()
        hashes=value['code_hashes']
        # Names are not selected by a request or arbitrary artifact path.
        expected={'app/automated/engine.py','app/automated/strategy.py','app/automated/service.py','app/automated/storage.py',
            'app/intelligence/market_context.py','research/market_intelligence/structure.py','app/intelligence/patterns.py',
            'app/lab/models.py','app/lab/indicators.py','app/lab/series.py','app/lab/execution.py'}
        if set(hashes)!=expected:raise ValueError()
        same=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha for p,sha in hashes.items())
        for key in ('isolated','historical'):
            if value[key].get('status') not in ALLOWED:raise ValueError()
            if not same:value[key].update(status='NOT_TESTED',reason='CODE_CHANGED_SINCE_VERIFICATION')
        # No recorded offline test or successful health check authorizes live PASS.
        value.update(live=empty['live'],read_only=True,test_only=True,live_execution_enabled=False,code_matches=same)
        return value
    except (OSError,ValueError,TypeError,KeyError):return dict(empty,reason='EVIDENCE_MISSING_OR_INVALID')

@router.get('',dependencies=[Depends(owner)])
async def report():
    return JSONResponse(await asyncio.to_thread(evidence),headers=HEADERS)
