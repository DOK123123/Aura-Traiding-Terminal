"""Fixed-rule causal fixtures; no optimization or claim of trading edge."""
from copy import deepcopy
import math
import numpy as np
import pytest

from app.hunter.market import SOURCE, STEPS
from app.manual_preview.market_regime import classify, adx14
from app.manual_preview.explainable import evaluate


def bars(kind, step=300):
    result=[]
    for i in range(260):
        c=1000+(i if kind=='up' else -i if kind=='down' else 2*math.sin(i) if kind=='flat'
                else (i if i<245 else 490-i))
        result.append([i*step,c-.1,c+2,c-2,c,10])
    return result


@pytest.mark.parametrize('frame,step',STEPS.items())
@pytest.mark.parametrize('kind,state',[('up','TREND_UP'),('down','TREND_DOWN'),('flat','RANGE'),('transition','TRANSITION')])
def test_regimes_all_native_timeframes_and_independent_sides(frame,step,kind,state):
    b=bars(kind,step);now=260*step
    regime=classify(b,frame,now)
    assert regime['state']==state
    assert regime['closed_at']==now and regime['closed_only'] is True
    assert regime['metrics']['range_width_atr']>0
    q=dict(source=SOURCE,bid=b[-1][4]-.01,ask=b[-1][4]+.01,last=b[-1][4],time=now,received_at=now)
    candidates=evaluate(b,frame,q,now)
    assert len(candidates)==6
    assert {x['direction'] for x in candidates}=={'LONG','SHORT'}
    assert all(x['market_regime']==regime for x in candidates)
    if state=='RANGE':
        trend=[x for x in candidates if x['strategy']=='TREND_PULLBACK']
        assert all(x['state']!='WATCH' and 'REGIME_RANGE_TREND_RESTRICTED' in x['rejection'] for x in trend)
        assert all('REGIME_RANGE_TREND_RESTRICTED' not in x['rejection'] for x in candidates if x not in trend)


@pytest.mark.parametrize('defect',['short','gap','nan','future','stale','zero_atr','clock'])
def test_unreliable_closed_data_unknown(defect):
    b=bars('up');at=260*300
    if defect=='short':b=b[-259:]
    if defect=='gap':b.pop(30)
    if defect=='nan':b[30][4]=float('nan')
    if defect=='future':b.append([at,1000,1002,998,1001,10])
    if defect=='stale':at+=300
    if defect=='zero_atr':b=[[r[0],1000,1000,1000,1000,10] for r in b]
    if defect=='clock':at=float('nan')
    assert classify(b,'5m',at)['state']=='UNKNOWN'


def test_adx_independent_directional_reference_and_equal_dm_ties():
    for kind in ['up','down']:
        # Constant directional +1/-1 movement and TR=4 imply DX and ADX=100.
        values=adx14(bars(kind))
        assert len(values)==260
        assert np.isnan(values[:27]).all()
        assert values[27:]==pytest.approx(np.full(233,100))
    flat=[[i*300,1000,1002,998,1000,10] for i in range(260)]
    assert adx14(flat)[27:]==pytest.approx(np.zeros(233))
    assert classify(flat,'5m',260*300)['state']=='RANGE'


def test_future_suffix_cannot_change_prefix_and_current_forming_bar_is_rejected():
    prefix=bars('transition');original=deepcopy(prefix);at=260*300
    expected=classify(prefix,'5m',at)
    suffix=[[at+i*300,1000,2000,500,1500,10] for i in range(10)]
    archive=prefix+suffix
    assert classify([r for r in archive if r[0]+300<=at],'5m',at)==expected
    suffix[0][4]=1999
    assert classify(archive,'5m',at)['state']=='UNKNOWN'
    assert prefix==original
