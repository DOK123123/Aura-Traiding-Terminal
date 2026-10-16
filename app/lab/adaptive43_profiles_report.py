"""Bounded immutable profile study reader; no simulation or account writes on GET."""
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
from .models import digest,LabError
from .adaptive43_report import FILES as ORIGINAL_FILES

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'docs/AURA43_PROFILES_COMPARISON.json.gz'
FILES=ORIGINAL_FILES+('app/lab/adaptive43_profiles.py','scripts/research_aura43_profiles.py',
 'scripts/aura43_history.py','scripts/aura43_profile_context.py','docs/AURA43_PROFILES_PROTOCOL.json',
 'scripts/replay_auto42_verification.py')

def software():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}

@lru_cache(maxsize=1)
def _load(path,mtime,size):
    if size>8*1024*1024:raise LabError('RESULT_LIMIT')
    try:
        with gzip.open(path,'rb') as f:raw=f.read(16*1024*1024+1)
        if len(raw)>16*1024*1024:raise ValueError()
        report=json.loads(raw);checksum=report.pop('checksum')
        if digest(report)!=checksum or report.get('symbol')!='BTCUSDT' or report.get('version')!='AURA43_PROFILES_1' or report.get('research_only') is not True or report.get('activation_available') is not False or report.get('real_money_execution')!='DISABLED':raise ValueError()
        if report.get('code_hashes')!=software():raise LabError('SOFTWARE_MISMATCH')
        if digest(report['development_selection'])!=report['selection_hash']:raise ValueError()
        return report
    except (OSError,EOFError,ValueError,KeyError,TypeError):raise LabError('CORRUPT_EXPERIMENT') from None

def load():
    try:
        stat=REPORT.stat();report=_load(str(REPORT),stat.st_mtime_ns,stat.st_size)
        if report.get('code_hashes')!=software():raise LabError('SOFTWARE_MISMATCH')
        return report
    except OSError:raise LabError('EXPERIMENT_NOT_FOUND') from None

def summary():
    r=load()
    return dict(**{k:v for k,v in r.items() if k!='runs'},runs=[{k:v for k,v in row.items() if k not in ('trades','equity_curve','decisions','daily_equity')} for row in r['runs']])

def detail(variant,split,offset,limit):
    row=next((r for r in load()['runs'] if r['variant']==variant and r['split']==split),None)
    if row is None:raise LabError('INVALID_DATA')
    return dict(**{k:v for k,v in row.items() if k not in ('trades','decisions')},
        trades=row['trades'][offset:offset+limit],trade_total=len(row['trades']),
        decisions=row['decisions'][offset:offset+limit],decision_total=len(row['decisions']),offset=offset,
        next_offset=offset+limit,has_more=offset+limit<max(len(row['trades']),len(row['decisions'])),
        research_only=True,activation_available=False,real_money_execution='DISABLED')
