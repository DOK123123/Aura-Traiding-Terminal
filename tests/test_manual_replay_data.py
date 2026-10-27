from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import csv,json
import pytest
from research.manual_analyst_replay.config import Config,digest
from research.manual_analyst_replay.dataset import Bar,Dataset,aggregate,load,sha256,SOURCE,validate
from research.manual_analyst_replay.adapter import build
from tests.test_manual_replay_engine import bar,T


def make_file(tmp_path,damage=None):
    p=tmp_path/'bars.csv'
    rows=[dict(time=T+i*60,open='100',high='101',low='99',close='100',volume='10',available_at=T+i*60+62) for i in range(480)]
    if damage=='gap':rows.pop(17)
    elif damage=='duplicate':rows[17]=rows[16]
    elif damage=='units':rows[17]['time']*=1000
    elif damage=='future_available':rows[-1]['available_at']=T+500000
    elif damage=='early':rows[17]['available_at']=rows[17]['time']+59
    elif damage=='nan':rows[17]['close']='NaN'
    with p.open('w') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    meta=dict(version=1,data_kind='SYNTHETIC_TEST',source=SOURCE,symbol='BTCUSDT',product_type='USDT-FUTURES',execution_step=60,
              availability_mode='OBSERVED',asof=T+600000,files=[dict(path=p.name,format='CSV',sha256=sha256(p))])
    m=tmp_path/'manifest.json';m.write_text(json.dumps(meta));return m


def test_strict_loader_aggregates_real_closed_bins_with_availability_and_provenance(tmp_path):
    p=make_file(tmp_path);d=load(p)
    assert len(d.execution)==480 and set(d.frames)=={'5m','15m','1h','4h'}
    b=d.frames['5m'][0];assert b.time==T and b.volume==50 and b.available_at==T+302
    assert len(d.frames['4h'])==2
    assert load(p).data_hash==d.data_hash
    with pytest.raises(ValueError,match='ROW_LIMIT'):load(p,max_rows=50)


@pytest.mark.parametrize('damage',['gap','duplicate','units','future_available','early','nan'])
def test_bad_candles_never_reach_analysis(tmp_path,damage):
    with pytest.raises(ValueError):load(make_file(tmp_path,damage))


def test_bad_hash_source_or_path_and_missing_available_data_fail(tmp_path):
    p=make_file(tmp_path);original=json.loads(p.read_text())
    for change in ['sha','source','path','availability']:
        meta=json.loads(json.dumps(original))
        if change=='sha':meta['files'][0]['sha256']='0'*64
        elif change=='source':meta['product_type']='SPOT'
        elif change=='path':meta['files'][0]['path']='../outside.csv'
        elif change=='availability':meta.pop('availability_mode')
        p.write_text(json.dumps(meta))
        with pytest.raises((ValueError,FileNotFoundError)):load(p)


def test_delayed_higher_timeframe_is_not_visible_at_decision_time(monkeypatch):
    # The 4h bar closing at cutoff has not yet been published; prefix must exclude it.
    from app.models import Candle
    from tests.test_aura_trader5_scenarios import windows,NOW
    from research.manual_analyst_replay import adapter
    context={}
    for tf,rows in windows().items():
        step={'5m':300,'15m':900,'1h':3600,'4h':14400}[tf]
        context[tf]=tuple(Bar(b.time,*map(lambda v:D(str(v)),(b.open,b.high,b.low,b.close,b.volume)),b.time+step+2) for b in rows)
    newest=context['5m'][-1];now=newest.available_at
    context['4h']=context['4h'][:-1]+(replace(context['4h'][-1],available_at=now+5),)
    d=Dataset((),60,context,{},'b'*64)
    called=[]
    monkeypatch.setattr(adapter,'assess',lambda *args,**kw:called.append(args))
    sig,dec=build(d,Config(),now,now+1,float('inf'))
    assert not sig and not called and dec[0]['reason']=='WARMUP_200_PER_FRAME'


def test_adapter_uses_original_analyst_and_same_prefix_after_future_append():
    from tests.test_aura_trader5_scenarios import windows,NOW
    from app.aura_trader5_scenarios import assess
    context={}
    for tf,rows in windows().items():
        step={'5m':300,'15m':900,'1h':3600,'4h':14400}[tf]
        context[tf]=tuple(Bar(b.time,*map(lambda v:D(str(v)),(b.open,b.high,b.low,b.close,b.volume)),b.time+step+2) for b in rows)
    now=context['5m'][-1].available_at
    d=Dataset((),60,context,{},'b'*64);s,dec=build(d,Config(),now,now+1,float('inf'))
    expected=assess(windows(),now)
    assert expected['state']=='LONG' and len(s)==1 and s[0].stop==D(str(expected['scenario']['stop_loss']))
    future=dict(context)
    for tf,step in [('5m',300),('15m',900),('1h',3600),('4h',14400)]:
        last=context[tf][-1];future[tf]+= (replace(last,time=last.time+step,available_at=last.available_at+step,close=last.close+D(1)),)
    assert build(replace(d,frames=future,data_hash='c'*64),Config(),now,now+1,float('inf'))==(s,dec)
