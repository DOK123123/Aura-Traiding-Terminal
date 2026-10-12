"""Offline validation tests for the isolated Binance CSV source."""
from pathlib import Path

import pytest

from app.lab.local_csv import load_binance_csv
from app.lab.models import LabError
from scripts.import_binance_csv import snapshot


BASE=1699992000  # UTC boundary aligned to 4h and 15m


def row(t, *, unit=1000, close=True, price="100"):
    t += BASE
    open_time=t*unit
    close_time=(t+900)*unit-1
    return [str(open_time), price, "101", "99", price, "10", str(close_time if close else open_time)]


def write(tmp_path: Path, rows, header=False):
    lines=[]
    if header:
        lines.append("open_time,open,high,low,close,volume,close_time")
    lines.extend(",".join(r) for r in rows)
    path=tmp_path/'BTCUSDT-15m-2026-09.csv'
    path.write_text("\n".join(lines)+"\n", encoding='utf-8')
    return path


def test_binance_csv_headerless_and_header_forms(tmp_path):
    rows=[row(i*900) for i in range(3)]
    bars, meta=load_binance_csv(write(tmp_path,rows))
    assert len(bars)==3 and not meta['header'] and bars[-1].time==BASE+1800
    bars, meta=load_binance_csv(write(tmp_path,rows,header=True))
    assert len(bars)==3 and meta['header']


def test_microsecond_timestamps_are_normalized(tmp_path):
    bars, _=load_binance_csv(write(tmp_path,[row(i*900,unit=1_000_000) for i in range(2)]))
    assert [bar.time for bar in bars]==[BASE,BASE+900]


@pytest.mark.parametrize('mutator,code', [
    (lambda rows: rows[:1]+rows[2:], 'MISSING_CANDLES'),
    (lambda rows: rows+[rows[1]], 'DUPLICATE_OR_UNORDERED'),
    (lambda rows: [rows[1],rows[0]], 'DUPLICATE_OR_UNORDERED'),
    (lambda rows: [['1.5']+rows[0][1:]], 'INVALID_TIMESTAMPS'),
    (lambda rows: [rows[0][:2]+['98']+rows[0][3:]], 'INVALID_OHLCV'),
    (lambda rows: [rows[0][:6]+['999']], 'INVALID_TIMESTAMPS'),
])
def test_csv_integrity_rejects_bad_rows(tmp_path, mutator, code):
    rows=mutator([row(i*900) for i in range(3)])
    with pytest.raises(LabError, match=code):
        load_binance_csv(write(tmp_path, rows))


def test_import_preserves_all_rows_and_marks_missing_lab_warmup(tmp_path):
    path=write(tmp_path,[row(i*900) for i in range(2880)])
    data=snapshot(path)
    assert data['local_csv']['rows_available']==2880
    assert data['base_count']==2880
    assert data['strategy_lab_compatible'] is False
    assert data['warmup_start'] is None


def test_lab_shape_requires_real_warmup_and_never_fabricates(tmp_path):
    path=write(tmp_path,[row(i*900) for i in range(2880)])
    with pytest.raises(LabError, match='INSUFFICIENT_WARMUP'):
        snapshot(path, start=BASE+4*3600)


def test_zero_volume_is_valid_and_future_or_forming_rows_rejected(tmp_path):
    records=[row(0)]
    records[0][5]='0'
    bars,_=load_binance_csv(write(tmp_path,records),now=BASE+900)
    assert bars[0].volume==0
    with pytest.raises(LabError,match='INVALID_TIMESTAMPS'):
        load_binance_csv(write(tmp_path,records),now=BASE+899)


@pytest.mark.parametrize('header',[
    'open_time,high,open,low,close,volume,close_time',
    'open_time,open,high,low,close,volume,garbage',
    'open_time,open,high,low,close,volume,close_time,extra',
])
def test_invalid_headers_rejected(tmp_path,header):
    path=write(tmp_path,[row(0)])
    path.write_text(header+'\n'+path.read_text())
    with pytest.raises(LabError,match='INVALID_HEADERS'):
        load_binance_csv(path)


@pytest.mark.parametrize('bad_value',['NaN','Infinity','-1','not-a-price'])
def test_invalid_numeric_values_rejected(tmp_path,bad_value):
    records=[row(0)];records[0][5]=bad_value
    with pytest.raises(LabError):load_binance_csv(write(tmp_path,records))


def test_resource_limits_checked_before_read_and_before_extra_rows(tmp_path,monkeypatch):
    import app.lab.local_csv as module
    path=write(tmp_path,[row(i*900) for i in range(3)])
    monkeypatch.setattr(module,'MAX_BYTES',1)
    with pytest.raises(LabError,match='LOCAL_FILE_TOO_LARGE'):load_binance_csv(path)
    monkeypatch.setattr(module,'MAX_BYTES',10000)
    monkeypatch.setattr(module,'MAX_ROWS',2)
    with pytest.raises(LabError,match='INVALID_ROW_COUNT'):load_binance_csv(path)


def test_binance_full_12_columns_and_mixed_units(tmp_path):
    records=[row(0)+['1000','5','2','200','0']]
    bars,_=load_binance_csv(write(tmp_path,records))
    assert len(bars)==1
    records[0][6]=str((BASE+900)*1000000-1)
    with pytest.raises(LabError,match='INVALID_TIMESTAMPS'):load_binance_csv(write(tmp_path,records))


def test_native_production_snapshot_compatibility(tmp_path):
    import json
    from scripts.diagnose_aura_auto import load_snapshot
    path=write(tmp_path,[row(i*900) for i in range(501)])
    data=snapshot(path,output_format='diagnostic')
    exported=tmp_path/'diagnostic.json'
    exported.write_text(json.dumps(data))
    bars,_,excluded=load_snapshot(exported,BASE+500*900,BASE+501*900,500)
    assert len(bars)==501 and excluded==0 and data['local_csv']['transport']=='local_file'


def test_existing_lab_backtester_accepts_local_snapshot(tmp_path):
    from app.lab.data import restore
    from app.lab.experiment import execute
    from app.lab.models import Baseline
    path=write(tmp_path,[row(i*900) for i in range(4096)])
    data=snapshot(path,output_format='lab',start=BASE+4000*900)
    assert len(restore(data))==4096
    report=execute(data,Baseline())
    assert report['base_count']==4096 and report['aura_comparison']=='INCOMPATIBLE'


def test_full_september_coverage_verified_without_truncation(tmp_path):
    from datetime import datetime,timezone
    start=int(datetime(2026,9,1,tzinfo=timezone.utc).timestamp())
    records=[row(start-BASE+i*900) for i in range(2880)]
    data=snapshot(write(tmp_path,records),month='2026-09')
    assert data['base_count']==2880 and not data['history_truncated']
    with pytest.raises(LabError,match='INCOMPLETE_MONTH'):
        snapshot(write(tmp_path,records[:-1]),month='2026-09')


def test_cli_never_overwrites_existing_output(tmp_path):
    from scripts.import_binance_csv import main
    csv_file=write(tmp_path,[row(0)])
    out=tmp_path/'output.json';out.write_bytes(b'preserve')
    with pytest.raises(SystemExit):main([str(csv_file),'--output',str(out)])
    assert out.read_bytes()==b'preserve'
