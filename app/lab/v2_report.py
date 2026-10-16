"""Owner-only immutable artifacts. No research job, account or market request."""
from functools import lru_cache
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
from .models import digest,LabError
from .adaptive43_report import FILES as ORIGINAL_FILES

ROOT=Path(__file__).resolve().parents[2]
DIRECTORY=ROOT/'docs/LAB_V2'
FILES=ORIGINAL_FILES+('scripts/replay_auto42_verification.py','scripts/aura43_profile_context.py','scripts/aura43_history.py','scripts/lab_v2_baselines.py',
    'app/lab/v2_strategies.py','app/lab/v2_execution.py','scripts/research_lab_v2.py','docs/STRATEGY_LAB_V2_PROTOCOL.json','scripts/research_aura43_profiles.py')
VARIANT=r'^(AURA42|AURA43|(DONCHIAN|TREND_ATR|EMA_RSI_ADX)_(15m|1h|4h))$'
SPLITS=('development','validation','full_12m','validation_delayed')

def software():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}

@lru_cache(maxsize=1)
def _load(path,mtime,size):
    if size>8*1024*1024:raise LabError('RESULT_LIMIT')
    try:
        with gzip.open(path,'rb') as f:raw=f.read(16*1024*1024+1)
        if len(raw)>16*1024*1024:raise ValueError()
        r=json.loads(raw);checksum=r.pop('checksum')
        if digest(r)!=checksum or r.get('version')!='AURA_STRATEGY_LAB_2.0' or r.get('symbol')!='BTCUSDT' or r.get('research_only') is not True or r.get('activation_available') is not False or r.get('real_money_execution')!='DISABLED':raise ValueError()
        if r.get('code_hashes')!=software():raise LabError('SOFTWARE_MISMATCH')
        if digest(r['development_selection'])!=r['selection_hash']:raise ValueError()
        return r
    except (OSError,EOFError,ValueError,KeyError,TypeError):raise LabError('CORRUPT_EXPERIMENT') from None

def load():
    try:
        path=DIRECTORY/'report.json.gz';s=path.stat();r=_load(str(path),s.st_mtime_ns,s.st_size)
        if r.get('code_hashes')!=software():raise LabError('SOFTWARE_MISMATCH')
        return r
    except OSError:raise LabError('EXPERIMENT_NOT_FOUND') from None

def summary():
    r=load()
    return dict(**{k:v for k,v in r.items() if k!='runs'},runs=[{k:v for k,v in row.items() if k not in ('trades','equity_curve','daily_equity')} for row in r['runs']])

def decision_page(row,offset,limit):
    expected='decisions_'+row['variant']+'_'+row['split']+'.jsonl.gz'
    if not re.fullmatch(VARIANT,row['variant']) or row['split'] not in SPLITS or row['decision_artifact']!=expected:raise LabError('CORRUPT_EXPERIMENT')
    try:
        path=DIRECTORY/expected
        if path.stat().st_size>4*1024*1024:raise ValueError()
        compressed=path.read_bytes()
        if len(compressed)>4*1024*1024 or hashlib.sha256(compressed).hexdigest()!=row['decision_sha256']:raise ValueError()
        selected=[];size=0;count=0
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            while True:
                line=stream.readline(32769)
                if not line:break
                size+=len(line)
                if len(line)>32768 or size>32*1024*1024 or count>=40000:raise ValueError()
                if offset<=count<offset+limit:selected.append(json.loads(line))
                count+=1
        if count!=row['decision_total']:raise ValueError()
        return selected
    except (OSError,EOFError,ValueError,KeyError,TypeError):raise LabError('CORRUPT_EXPERIMENT') from None

def detail(variant,split,offset,limit,side='ALL'):
    r=load();row=next((x for x in r['runs'] if x['variant']==variant and x['split']==split),None)
    if row is None or side not in ('ALL','LONG','SHORT'):raise LabError('INVALID_DATA')
    trades=[t for t in row['trades'] if side=='ALL' or t['direction']==side]
    return dict(**{k:v for k,v in row.items() if k!='trades'},trades=trades[offset:offset+limit],trade_total=len(trades),
        decisions=decision_page(row,offset,limit),offset=offset,next_offset=offset+limit,
        has_more=offset+limit<max(len(trades),row['decision_total']),side=side,
        research_only=True,activation_available=False,real_money_execution='DISABLED')
