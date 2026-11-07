"""Research outcome model: independent boundary fixtures, never terminal orders."""
from scripts.audit_aura5_regime import outcome


def test_audit_next_open_and_stop_first():
    p=dict(index=0,direction='LONG',sl=98,tp=108,hold=1,zone=[99,101])
    bars=[[0,100,200,1,100,1],[300,100,109,97,101,1],[600,100,101,99,100,1]]
    assert outcome(p,bars,300,1)['state']=='SL'
    bars[1]=[300,110,111,109,110,1]
    assert outcome(p,bars,300,1)=={'state':'NO_FILL'}


def test_audit_adverse_stop_gap_and_right_censoring():
    p=dict(index=0,direction='LONG',sl=98,tp=108,hold=2,zone=[99,101])
    bars=[[0,100,200,1,100,1],[300,100,101,99,100,1],[600,95,96,94,95,1],[900,100,101,99,100,1]]
    result=outcome(p,bars,300,1)
    assert result['state']=='SL' and result['net_r'] < -1
    assert outcome(p,bars[:2],300,1)=={'state':'RIGHT_CENSORED'}
