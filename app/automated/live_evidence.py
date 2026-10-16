"""Immutable, code-bound isolated-test evidence; never executes a test on GET."""
import hashlib
import json
from pathlib import Path
from app.lab.models import digest

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'docs/AURA_LIVE_PAPER_TECHNICAL_VERIFICATION.json'
FILES=('app/automated/engine.py','app/automated/strategy.py','app/automated/service.py',
    'app/automated/storage.py','app/automated/live_monitor.py','scripts/verify_live_paper_monitor.py')


def code_hashes() -> dict:
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}


def evidence() -> dict:
    empty=dict(status='NOT_TESTED',test_only=True,proves_live_autonomy=False)
    try:
        if REPORT.stat().st_size>128*1024:raise ValueError()
        value=json.loads(REPORT.read_bytes());checksum=value.pop('checksum')
        if checksum!=digest(value) or value.get('code_hashes')!=code_hashes():raise ValueError()
        if value.get('test_only') is not True or value.get('status') not in ('PASS','FAIL'):raise ValueError()
        return dict(value,proves_live_autonomy=False)
    except (OSError,ValueError,KeyError,TypeError):return empty
