"""Read existing PR5 real-data artifact; no provider changes or network fetches."""
from functools import lru_cache
import gzip
import hashlib
from pathlib import Path
import tempfile
from scripts.aura43_history import load_history
from app.lab.models import LabError,validate_series
from .registry import PROTOCOL

ROOT=Path(__file__).resolve().parents[2]
DATASET='LAB_V2_BTCUSDT_15m'
SHA='da31330b7d5df5bf9560171372e6f4157d3215ef236ef528a529089f6a823810'

def available() -> dict:
    return dict(id=DATASET,symbol='BTCUSDT',source='Binance Spot public REST data-api.binance.vision/api/v3/klines',
        start=PROTOCOL['start'],end_exclusive=PROTOCOL['end_exclusive'],evaluation_days=365,evaluation_candles=35040,
        warmup_candles=4160,total_candles=39200,timeframes=['15m','1h','4h'],aggregation='1h/4h: complete UTC bins from same15m source',
        sha256=SHA,provenance='docs/data/LAB_V2_DATA_PROVENANCE.json',independent_test_available=False,
        test_status='REUSED_EXPLORATORY_TEST',previous_research=['main historical research','PR3','PR4','PR5'])

@lru_cache(maxsize=1)
def load_dataset():
    try:
        with gzip.open(ROOT/'docs/data/LAB_V2_BTCUSDT_15m.csv.gz','rb') as stream:raw=stream.read(12*1024*1024+1)
        if len(raw)>12*1024*1024 or hashlib.sha256(raw).hexdigest()!=SHA:raise LabError('DATA_INTEGRITY')
        with tempfile.TemporaryDirectory(prefix='aura-research-data-') as folder:
            p=Path(folder)/'history.csv';p.write_bytes(raw);bars,source=load_history(p)
        if len(bars)!=39200 or bars[0].time!=PROTOCOL['start']-4160*900 or bars[-1].time+900!=PROTOCOL['end_exclusive']:raise LabError('DATA_INTEGRITY')
        validate_series(bars,900,PROTOCOL['end_exclusive'])
        return tuple(bars),dict(available(),**source)
    except (OSError,ValueError):raise LabError('DATA_UNAVAILABLE') from None
