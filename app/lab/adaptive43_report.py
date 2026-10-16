"""Read-only, bounded Strategy Lab artifact. No live client or research job on GET."""
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
from .models import digest,LabError

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'docs/AURA43_COMPARISON.json.gz'
FILES=('app/lab/adaptive43.py','scripts/research_aura43.py','docs/AURA43_PROTOCOL.json',
    'app/automated/engine.py','app/automated/strategy.py','app/intelligence/market_context.py',
    'app/automated/alignment.py','research/market_intelligence/structure.py','app/intelligence/patterns.py',
    'app/lab/indicators.py','app/lab/models.py','app/lab/series.py','app/lab/execution.py')


def software():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}


@lru_cache(maxsize=1)
def _load(path,mtime,size):
    if size>8*1024*1024:raise LabError('RESULT_LIMIT')
    try:
        with gzip.open(path,'rb') as f:raw=f.read(24*1024*1024+1)
        if len(raw)>24*1024*1024:raise ValueError()
        report=json.loads(raw);checksum=report.pop('checksum')
        if digest(report)!=checksum or report.get('symbol')!='BTCUSDT' or report.get('research_only') is not True or report.get('activation_available') is not False or report.get('real_money_execution')!='DISABLED':raise ValueError()
        if report.get('code_hashes')!=software():raise LabError('SOFTWARE_MISMATCH')
        return report
    except (OSError,EOFError,ValueError,KeyError,TypeError):raise LabError('CORRUPT_EXPERIMENT') from None


def load():
    try:
        stat=REPORT.stat();report=_load(str(REPORT),stat.st_mtime_ns,stat.st_size)
        if report.get('code_hashes')!=software():raise LabError('SOFTWARE_MISMATCH')
        return report
    except OSError:raise LabError('EXPERIMENT_NOT_FOUND') from None


def summary():
    report=load()
    return dict(**{k:v for k,v in report.items() if k!='runs'},
        runs=[{k:v for k,v in r.items() if k not in ('trades','equity_curve','decisions','daily_equity')} for r in report['runs']])


def detail(variant,split,offset,limit):
    report=load();row=next((r for r in report['runs'] if r['variant']==variant and r['split']==split),None)
    if row is None:raise LabError('INVALID_DATA')
    return dict(**{k:v for k,v in row.items() if k not in ('trades','decisions')},
        trades=row['trades'][offset:offset+limit],trade_total=len(row['trades']),
        decisions=row['decisions'][offset:offset+limit],decision_total=len(row['decisions']),
        offset=offset,next_offset=offset+limit,has_more=offset+limit<max(len(row['trades']),len(row['decisions'])),
        research_only=True,activation_available=False,real_money_execution='DISABLED')
