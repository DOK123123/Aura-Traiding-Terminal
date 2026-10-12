"""Diagnostic code checks; synthetic fixtures are not strategy performance data."""
from types import SimpleNamespace
import math
import numpy as np

from app.patterns.config import PatternConfig
from app.patterns.matching import find_matches
from scripts.audit_pattern_math import trace,distribution,summarize


def test_diagnostic_selection_matches_production_at_all_thresholds():
    rng=np.random.default_rng(25)
    features=SimpleNamespace(vectors=rng.uniform(-.3,.3,(2000,121)),valid_from=499)
    _,selection,available=trace(features,1999,PatternConfig())
    assert available==1431
    for s in (60,65,70,75,80,85):
        assert selection[s][:100]==find_matches(features,1999,PatternConfig(minimum_similarity=s))


def test_similarity_group_weights_and_percent_units_independent_oracle():
    vectors=np.zeros((600,121));vectors[499,21:]=1
    features=SimpleNamespace(vectors=vectors,valid_from=499)
    scores,_,count=trace(features,599,PatternConfig())
    assert count==31
    assert abs(scores[0]-100*math.exp(-3/math.sqrt(2)))<1e-12
    assert scores[1]==100


def test_purge_boundary_and_tie_order_match_window_lengths():
    features=SimpleNamespace(vectors=np.zeros((800,121)),valid_from=499)
    _,selected,_=trace(features,799,PatternConfig())
    assert [m['index'] for m in selected[75]]==[499,569,639,709]
    assert all(m['index']+50<799-20+1 for m in selected[75])


def test_intersections_do_not_count_minimum_sample_as_unique_cause():
    records=[dict(selected=0,similarity_pass=0,post_purge_uncapped=0,available_windows=100,
                  nearest_similarity=60,signal='WAIT',confidence_raw=0,
                  failed_filters=['MINIMUM_SAMPLE','CONFIDENCE','WILSON']) for _ in range(2)]
    result=summarize(records)
    assert result['pair_intersections']['CONFIDENCE & MINIMUM_SAMPLE']==2
    assert result['sole_blocker']['MINIMUM_SAMPLE']==0
    assert result['without_sample_gate_signals']==0
    assert distribution([0,0,1,3])==dict(minimum=0,median=.5,mean=1,maximum=3,histogram={'0':2,'1':1,'3':1})
