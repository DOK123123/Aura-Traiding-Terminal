"""Exact reference equivalence, not profit tests or a timing-based acceptance test."""
from decimal import Decimal,localcontext
from unittest.mock import patch
import random
from research.market_intelligence.structure import zones,segment_states
from app.lab.series import higher
from app.lab.models import digest
from tests.test_market_context import fixture


def reference(pivots,tolerance):
    groups=[]
    for pivot in sorted(pivots[-32:],key=lambda p:p['price']):
        if groups and abs(pivot['price']-sum(p['price'] for p in groups[-1])/len(groups[-1]))<=tolerance:groups[-1].append(pivot)
        else:groups.append([pivot])
    return [dict(price=sum(p['price'] for p in g)/len(g),touches=len(g),confirmed_at=max(p['confirmation_time'] for p in g)) for g in groups]


def test_decimal_clusters_match_original_all_prefixes_and_precisions():
    rng=random.Random(42)
    for precision in (8,16,28,50):
        with localcontext() as ctx:
            ctx.prec=precision
            for length in (0,1,2,7,32,50):
                pivots=[dict(price=Decimal(rng.randrange(1,1000000))/Decimal(97),confirmation_time=i) for i in range(length)]
                for tolerance in (Decimal(0),Decimal('.1'),Decimal(10),Decimal('100000')):
                    assert zones(pivots,tolerance)==reference(pivots,tolerance)


def test_full_market_states_unchanged_across_all_three_frames():
    bs=fixture(4175)
    for step in (900,3600,14400):
        frame=bs if step==900 else higher(bs,step)
        actual=segment_states(frame,step)
        with patch('research.market_intelligence.structure.zones',reference):expected=segment_states(frame,step)
        assert digest(actual)==digest(expected)


def test_rebind_rejects_unknown_input_without_writing(tmp_path):
    from scripts.rebind_analog_software import rebind
    import pytest
    src=tmp_path/'unknown.gz';src.write_bytes(b'not the verified original');out=tmp_path/'out.gz'
    with pytest.raises(ValueError,match='UNEXPECTED_INPUT'):rebind(src,out)
    assert not out.exists()


def test_dense_cluster_avoids_repeated_prefix_sums():
    from unittest.mock import patch
    original_sum=sum
    pivots=[dict(price=Decimal('100')+Decimal(i)/1000,confirmation_time=i) for i in range(32)]
    with patch('builtins.sum',wraps=original_sum) as calls:
        optimized=zones(pivots,Decimal(1));optimized_calls=calls.call_count
    with patch('builtins.sum',wraps=original_sum) as calls:
        old=reference(pivots,Decimal(1));old_calls=calls.call_count
    assert optimized==old
    assert optimized_calls==1
    assert old_calls==32
