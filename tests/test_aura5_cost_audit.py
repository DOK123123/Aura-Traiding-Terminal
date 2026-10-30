"""Independent arithmetic and invariant tests; no orders or parameter optimization."""
from decimal import Decimal as D
import copy
import pytest

from app.hunter.costs import risk_reward,entry_fill
from app.hunter.engine import net_rr,Prepared
from app.hunter.outcomes import cashflow,simulate
from app.hunter.store import Store,MODEL_HASH
from tests.test_hunter6 import plan,quote
from tests.test_hunter6_forward import sample
from research.aura5_cost_audit.baseline import engine as old


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_cost_rr_matches_independent_decimal_quote_side_arithmetic(side):
    s=D(1) if side=='LONG' else D(-1)
    stop=D(100)-s*D(10);target=D(100)+s*D(20)
    # Ask/Bid is already executable; no second spread on either quote threshold.
    e=D(100)*(1+s*D('.0005'));sl=stop*(1-s*D('.0005'));tp=target*(1-s*D('.0005'))
    loss=s*(e-sl)+D('.001')*(e+sl)+D('.01')
    win=s*(tp-e)-D('.001')*(e+tp)-D('.01')
    assert net_rr(100,float(stop),float(target),side,300,3,spread=.02)==pytest.approx(float(win/loss),abs=1e-12)
    # OHLC entry pays half spread exactly once, compounding actual slippage.
    filled=D(100)*(1+s*D('.0001'))*(1+s*D('.0005'))
    assert entry_fill(100,side)==pytest.approx(float(filled),abs=1e-12)
    assert risk_reward(100,float(stop),float(target),side,300,3)['entry_fill']==pytest.approx(float(filled))
    assert net_rr(100,float(stop),float(target),side,300,3,spread=.02)>old.net_rr(100,float(stop),float(target),side,300,3,spread=.02)


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_planned_exit_quote_rr_matches_cashflows_at_exact_tp_sl(side):
    p=plan(side);cost=risk_reward(100,p['sl'],p['tp'],side,300,p['hold_bars'])
    # A non-settlement interval: reserve is explicitly not an observed funding fee.
    base=[[96000,100,125,75,100,1]]
    for key,expected in [('stop_fill',-cost['net_loss']),('target_fill',cost['net_reward'])]:
        out=cashflow(p,cost['entry_fill'],cost[key],96000,96000,base,[])
        assert float(out['pnl_usdt'])-cost['funding_reserve']==pytest.approx(expected,abs=1e-10)
        assert float(out['risk_usdt'])>abs(p['entry']-p['sl'])


def test_post_exit_funding_not_charged_but_timeout_boundary_debit_retained():
    p=plan(at=86100);bs=[[86100,100,102,98,101,1]]
    assert cashflow(p,100,110,86100,86100,bs,[[86400,.01]])['funding_usdt']=='0'
    assert cashflow(p,100,110,86100,86100,bs,[])['missing_funding_settlements']==0
    out=cashflow(p,100,110,86100,86100,bs,[[86400,.01]],exit_at_close=True)
    assert float(out['funding_usdt'])==pytest.approx(1.02)


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_entry_rechecks_net_rr_expiry_and_slippage_geometry(side):
    p=plan(side);sign=1 if side=='LONG' else -1
    # Inside zone and levels but shifted entry makes net RR fall below 1.5.
    price=104 if sign==1 else 96
    bs=[[96000,price,price+1,price-1,price,1]]
    assert old.net_rr(price,p['sl'],p['tp'],side,300,3)<1.5
    assert simulate(p,bs,[])['note']=='FILLED_GEOMETRY_ZONE_OR_NET_RR'
    assert simulate(p,[[96300,100,101,99,100,1]],[],delay=2)['note']=='ENTRY_EXPIRED'
    p['zone']=[99.999,100.001]
    assert simulate(p,[[96000,100,101,99,100,1]],[])['outcome']=='NO_FILL'


def test_old_model_records_are_preserved_but_not_actionable(tmp_path,monkeypatch):
    p=plan();monkeypatch.setattr(Prepared,'plans',lambda self,i,family,**kw:[copy.deepcopy(p)] if family=='TREND_PULLBACK' else [])
    store=Store(tmp_path/'version.sqlite');store.observe(sample(),[],96001.,{'approved':[]})
    with store.connection() as db:
        import json
        r=db.execute('SELECT id,payload FROM events').fetchone();payload=json.loads(r['payload'])
        payload['plan']['model_sha256']='0'*64
        db.execute('UPDATE events SET payload=? WHERE id=?',(json.dumps(payload),r['id']))
    snap=store.snapshot(96001.,{'5m':quote(96001.)})
    assert snap['records'][0]['state']=='NO TRADE' and snap['watch_alerts']==[] and snap['alerts']==[]
    assert snap['records'][0]['recorded_state']=='WATCH'


@pytest.mark.parametrize('kwargs',[{'direction':'INVALID'},{'direction':True},{'spread':-1},{'spread':float('nan')},{'hold':0},{'step':True}])
def test_invalid_cost_contract_fails_closed(kwargs):
    args=dict(entry=100,stop=90,target=120,direction='LONG',step=300,hold=3,spread=None);args.update(kwargs)
    assert risk_reward(**args) is None


def test_live_snapshot_refreshes_quote_rr_and_refuses_slippage_outside_zone(tmp_path,monkeypatch):
    p=plan();monkeypatch.setattr(Prepared,'plans',lambda self,i,family,**kw:[copy.deepcopy(p)] if family=='TREND_PULLBACK' else [])
    store=Store(tmp_path/'fresh.sqlite');store.observe(sample(),[],96001.,{'approved':[]})
    snap=store.snapshot(96002.,{'5m':quote(96002.,101)})
    rr=net_rr(101.01,p['sl'],p['tp'],'LONG',300,p['hold_bars'],.02)
    assert snap['records'][0]['plan']['net_rr_at_quote']==pytest.approx(rr)
    # Entry Ask lies in the zone; actual modeled fill would leave it.
    p['zone']=[99.9,100.02]
    other=Store(tmp_path/'zone.sqlite');other.observe(sample(),[],96001.,{'approved':[]})
    assert other.snapshot(96001.,{'5m':quote(96001.)})['state']=='NO TRADE'


def test_baseline_sources_are_exact_and_strategy_parameters_unchanged():
    import hashlib
    from pathlib import Path
    from research.aura5_cost_audit.baseline import MODEL_HASH as original
    assert original=='fa700ebbbff6fbb4af411389fd38a145ea2ec4a63ad930a27f8302a771aaed83'
    assert Path('app/hunter/rules.json').read_bytes()==Path('research/aura5_cost_audit/baseline/rules.json').read_bytes()
    for name in ['engine.py','outcomes.py','diagnostics.py']:
        assert hashlib.sha256(Path('research/aura5_cost_audit/baseline',name).read_bytes()).hexdigest()=={'engine.py': '2668c667dd166177b8f6ecc928dd74ee6efa8b4ec728aef633a38828559c851e', 'outcomes.py': 'e8af59c0bbd29a70f6e8dfb42ffbb1266cf3b32ec721906d9e880633c6c9db9a', 'diagnostics.py': 'e0bf2674219d79c9afc4e18e1e50ebeadaafa3cb124df70a747d841ae8d1601d'}[name]


@pytest.mark.parametrize('side,rate',[('LONG',.0001),('SHORT',-.0001)])
def test_funding_debit_sign_and_stress_are_symmetric(side,rate):
    p=plan(side,at=86400);bs=[[86400,100,102,98,100,1]]
    a=cashflow(p,100,100,86400,86400,bs,[[86400,rate]])
    b=cashflow(p,100,100,86400,86400,bs,[[86400,rate]],multiplier=2)
    assert float(a['fees_usdt'])==pytest.approx(.2)
    assert float(a['funding_usdt'])==pytest.approx(.0102)
    assert float(b['pnl_usdt'])==pytest.approx(2*float(a['pnl_usdt']))
    assert b['risk_definition']==a['risk_definition']


def test_real_bitget_229_replay_reproduces_cost_audit_without_tuning(tmp_path):
    import gzip
    import json
    from pathlib import Path
    from research.aura5_cost_audit.run import run,P
    out=tmp_path/'audit'
    s=run(out,start=P['issue66_window'][0],end=P['issue66_window'][1])
    assert s['issue66_candidates_audited']==229
    assert s['issue66_before_admitted']==0 and s['issue66_after_admitted']==2
    audited=json.loads(gzip.decompress((out/'candidates229.json.gz').read_bytes()))
    assert all(not r['after']['technical_trigger'] for r in audited if r['after']['rejection'] is None)
    assert s['approved_for_confirmed']==[] and s['orders']==0 and not s['independent_unseen_oos']
    saved=Path('docs/aura_trader5/cost_audit/results')
    assert (out/'candidates229.csv').read_bytes()==(saved/'candidates229.csv').read_bytes()
    assert (out/'candidates229.json.gz').read_bytes()==(saved/'candidates229.json.gz').read_bytes()


def test_saved_full_comparison_has_real_long_short_and_reconciles_cashflows():
    import gzip
    import json
    from pathlib import Path
    root=Path('docs/aura_trader5/cost_audit/results')
    summary=json.loads((root/'summary.json').read_text())
    trades=json.loads(gzip.decompress((root/'outcomes.json.gz').read_bytes()))
    assert summary['model_sha256']==MODEL_HASH and summary['closed_windows']==36846
    assert summary['no_strategy_parameter_changes'] and summary['orders']==0
    for total in summary['totals']:
        records=[r for r in trades if r['audit_version']==total['version'] and r['cost_multiplier']==total['cost_multiplier']]
        closed=[r for r in records if r.get('pnl_usdt') is not None and r['outcome'] in ('TP','SL','TIMEOUT')]
        assert len(records)==total['signals'] and len(closed)==total['closed']
        assert {r['direction'] for r in closed}=={'LONG','SHORT'}
        assert sum(D(r['pnl_usdt']) for r in closed)==pytest.approx(D(str(total['net_pnl_usdt_per_independent_1btc'])),abs=D('0.000001'))
        for r in closed:
            sign=D(1 if r['direction']=='LONG' else -1)
            expected=sign*(D(str(r['exit_fill']))-D(str(r['entry_fill'])))-D(r['fees_usdt'])-D(r['funding_usdt'])
            assert D(r['pnl_usdt'])==pytest.approx(expected,abs=D('0.0000001'))
            assert r['missing_funding_settlements']==0
