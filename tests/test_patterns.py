"""Synthetic fixtures are ONLY unit tests, never runtime data sources."""
import asyncio
from dataclasses import replace
import math
import time

from fastapi.testclient import TestClient
import numpy as np
import pytest
from pydantic import ValidationError

from app.main import app
from app.models import Candle
from app.patterns.config import PatternConfig
from app.patterns.features import build_features, multi_timeframe
from app.patterns.matching import find_matches
from app.patterns.outcomes import outcome, statistics
from app.patterns.signals import decide
from app.patterns.engine import evaluate
from app.patterns.backtesting import replay
from app.patterns.history import Archive, Dataset, history_service, HistoryService
from app.providers import DataUnavailable


def bars(n=1500):
    result=[]
    origin=int(time.time())//60*60-n*60
    for i in range(n):
        op=100+2*math.sin(i/15)+.001*i
        close=op+.2*math.cos(i/7)
        result.append(Candle(origin+i*60,op,max(op,close)+.1,min(op,close)-.1,close,100+i%30))
    return result


def test_features_invariant_to_absolute_price_and_volume_scale():
    candles=bars(700)
    scaled=[Candle(c.time,c.open*23,c.high*23,c.low*23,c.close*23,c.volume*10) for c in candles]
    a,b=build_features(candles),build_features(scaled)
    np.testing.assert_allclose(a.vectors,b.vectors,atol=1e-9,equal_nan=True)


def test_future_mutation_cannot_change_features_matches_or_prediction():
    candles=bars(1500); target=1200
    changed=candles[:target+1]+[Candle(c.time,c.open*5,c.high*5,c.low*5,c.close*5,None) for c in candles[target+1:]]
    config=PatternConfig(minimum_similarity=0)
    baseline=evaluate(candles,60,500,config,target)
    assert baseline==evaluate(changed,60,500,config,target)
    assert baseline==evaluate(candles[:target+1],60,500,config,target)


def test_purging_and_non_overlapping_outcomes():
    config=PatternConfig(minimum_similarity=0)
    features=build_features(bars(2000))
    matches=find_matches(features,1999,config)
    assert matches
    for m in matches:
        assert m['index']+max(config.horizons)<1999-config.lookback+1
        assert m['index']>=features.valid_from
    for i,a in enumerate(matches):
        for b in matches[i+1:]: assert abs(a['index']-b['index'])>=config.lookback+max(config.horizons)


def test_outcome_counts_flat_and_excursions_are_exact():
    candles=[Candle(0,100,100,100,100,None),Candle(60,100,110,90,105,None),Candle(120,105,108,100,100,None)]
    assert outcome(candles,0,2)==pytest.approx(dict(move_pct=0,mfe_pct=10,mae_pct=-10))
    result=statistics(candles,[dict(index=0)],(1,2))
    assert result['1']['up']==1 and result['2']['flat']==1
    assert result['2']['max_positive_pct']==0
    assert outcome(candles,2,1) is None


def test_small_sample_and_no_edge_force_wait():
    config=PatternConfig()
    facts=build_features(bars(600)).facts[-1]
    def run(n,up):
        s=dict(count=n,up=up,down=n-up,flat=0,up_pct=100*up/n,down_pct=100*(n-up)/n,
               average_move_pct=.5,median_move_pct=.4)
        return decide({str(h):s for h in config.horizons},[dict(similarity=99)]*n,facts,[],config)
    small=run(5,5)
    assert small['signal']=='WAIT' and small['low_sample_size'] and small['confidence']<25
    weak=run(100,51)
    assert weak['signal']=='WAIT'
    assert run(100,90)['confidence']>small['confidence']


def test_missing_volume_excluded_without_nan_json():
    candles=[replace(c,volume=None) for c in bars(1000)]
    result=evaluate(candles,60,500,PatternConfig(minimum_similarity=0))
    assert not result['features']['volume_available']
    import json
    json.dumps(result,allow_nan=False)


def test_multi_timeframe_uses_only_complete_closed_buckets():
    candles=bars(1800);target=1601
    result=multi_timeframe(candles,target,60)
    assert result==multi_timeframe(candles[:target+1],target,60)
    for item in result:
        if 'last_closed_at' in item: assert item['last_closed_at']<=candles[target].time+60


@pytest.mark.parametrize('settings',[dict(lookback=1),dict(horizons=(5,5,20)),dict(horizons=(5,10)),dict(signal_threshold=50),dict(minimum_sample=0)])
def test_config_rejects_invalid_values(settings):
    with pytest.raises(ValidationError):PatternConfig(**settings)


@pytest.mark.parametrize('side,direction', [('LONG',1),('SHORT',-1)])
def test_strong_evidence_can_produce_both_directions(side,direction):
    config=PatternConfig()
    facts=build_features(bars(600)).facts[-1]
    facts['volatility_ratio']=1
    stat=dict(up=90 if direction==1 else 10,down=10 if direction==1 else 90,flat=0,
              up_pct=90 if direction==1 else 10,down_pct=10 if direction==1 else 90,
              average_move_pct=direction*.5,median_move_pct=direction*.4)
    result=decide({str(h):stat for h in config.horizons},[dict(similarity=95)]*100,facts,[],config)
    assert result['signal']==side and result['confidence']>config.minimum_confidence


def test_default_archive_stays_in_project():
    from app.patterns.history import DB_PATH
    from pathlib import Path
    assert DB_PATH.parent.parent==Path(__file__).resolve().parents[1]


def test_archive_separates_sources_and_upserts(tmp_path):
    archive=Archive(tmp_path/'test.sqlite3');rows=bars(5)
    archive.save('XAUUSD','1m','A',rows)
    archive.save('XAUUSD','1m','B',[replace(c,volume=None) for c in rows])
    archive.save('XAUUSD','1m','A',rows)
    assert archive.read('XAUUSD','1m','A')==rows
    assert len(archive.read('XAUUSD','1m','B'))==5
    assert archive.read('XAUUSD','1m','B')[0].volume is None


def test_backtest_next_open_costs_drawdown_and_wait(monkeypatch):
    candles=bars(700); start=550;horizon=20
    # Prices deliberately distinguish next-open execution from decision close.
    candles[start+1]=Candle(candles[start+1].time,100,200,50,100,10)
    candles[start+horizon]=Candle(candles[start+horizon].time,100,200,50,110,10)
    candles[start+horizon+1]=Candle(candles[start+horizon+1].time,100,200,50,100,10)
    candles[start+2*horizon]=Candle(candles[start+2*horizon].time,100,200,50,90,10)
    def decision(rows,step,context,config,target,*args):
        return dict(signal='LONG' if target<start+2*horizon else 'WAIT',as_of=rows[target].time+60,
                    confidence=70,historical_matches=30)
    monkeypatch.setattr('app.patterns.backtesting.evaluate',decision)
    result=replay(candles,60,500,PatternConfig(),start_at=candles[start].time+60,max_points=3)
    stats=result['summary']
    assert stats['total_signals']==2 and stats['wins']==1 and stats['losses']==1
    assert stats['average_return_pct']==pytest.approx(-.05)
    assert stats['max_drawdown_pct']==pytest.approx(10.05)
    assert stats['profit_factor']==pytest.approx(9.95/10.05)
    assert stats['wait_frequency']==pytest.approx(100/3)
    assert result['points'][0]['entry_time']==candles[start+1].time


def test_api_real_failure_no_fictitious_signal(monkeypatch):
    async def unavailable(*a):raise DataUnavailable('upstream offline')
    monkeypatch.setattr(history_service,'get',unavailable)
    with TestClient(app) as client:
        response=client.post('/api/patterns/analyze',json={})
        assert response.status_code==503
        assert response.json()['status']=='NO DATA'
        assert response.json()['signal'] is None and response.json()['confidence'] is None


def test_api_point_replay_and_delayed_data(monkeypatch):
    candles=bars(1500)
    async def dataset(*a):return Dataset(candles,'Binance · Spot',time.time(),1500,'test fixture')
    monkeypatch.setattr(history_service,'get',dataset)
    with TestClient(app) as client:
        data=client.post('/api/patterns/analyze',json={'timeframe':'1m','as_of':candles[1200].time+60}).json()
        assert data['mode']=='POINT REPLAY' and data['archive_available_at_decision']==1201
        assert data['actual_after_point']['20'] is not None
        assert all(m['time']<data['query_time'] for m in data['top_matches'])
        candles[:]=[replace(c,time=c.time-3600) for c in candles]
        delayed=client.post('/api/patterns/analyze',json={'timeframe':'1m','chart_source':'Binance · Spot'}).json()
        assert delayed['status']=='DELAYED' and delayed['signal']=='WAIT'
        assert client.post('/api/patterns/analyze',json={'config':{'horizons':[0]}}).status_code==422
