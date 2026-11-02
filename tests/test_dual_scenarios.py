"""Frozen rules decide acceptance; a high directional score cannot override them."""
from app.hunter.dual import complete_sides, qualify_sides
from app.hunter.engine import Prepared, FAMILIES
from app.hunter.confidence import technical_scores
from tests.test_hunter_confidence import history, quote


def test_missing_data_has_eight_unknown_sides():
    rows=complete_sides([], 'OBSERVER_STOPPED')
    assert len(rows)==8
    for row in rows:
        assert row['state']=='UNKNOWN'
        assert all(row[k] is None for k in ('score','entry','sl','tp','net_rr'))
        assert row['edge_status']=='NO_EDGE_FOUND'


def test_high_score_without_rule_trigger_is_rejected():
    bars=history()[-260:];p=Prepared(bars,'5m');now=bars[-1][0]+301;q=quote(now,bars[-1][4])
    plans=[plan for family in FAMILIES for plan in p.plans(259,family,watch=True)]
    rows=qualify_sides(technical_scores(p,q,now),p,plans,q,now)
    assert {r['direction'] for r in rows}=={'LONG','SHORT'}
    assert all(r['state']=='REJECTED' for r in rows)
    assert all(r['rejection_reasons'] for r in rows)
    assert all(not r['risk_gates_passed'] for r in rows)
    assert all(r['edge_status']=='NO_EDGE_FOUND' for r in rows)
    assert len(complete_sides(rows))==8


def test_both_directions_require_trigger_zone_costs_and_minimum_rr(monkeypatch):
    import app.hunter.dual as dual
    bars=history()[-260:];p=Prepared(bars,'5m');now=bars[-1][0]+301;q=quote(now,bars[-1][4])
    # Isolate planning gates; actual frozen predicate equivalence is tested in diagnostics.
    monkeypatch.setattr(dual,'predicates',lambda *args: ({'SETUP':True},{'TRIGGER':True}))
    for side, sign in [('LONG',1),('SHORT',-1)]:
        entry=q['ask' if sign==1 else 'bid']
        plan={'strategy':FAMILIES[0],'direction':side,'sl':entry-sign*400,'tp':entry+sign*2000,
              'zone':[entry-100,entry+100],'hold_bars':24,'valid_until':now+100,'technical_trigger':True}
        def run(overrides=None):
            score=next(c for c in technical_scores(p,q,now) if c['direction']==side)
            score['score']=80
            return qualify_sides([score],p,[{**plan,**(overrides or {})}],q,now)[0]
        accepted=run()
        assert accepted['state']=='WATCH_RESEARCH'
        assert accepted['net_rr']>=1.5
        assert accepted['entry']==entry
        assert accepted['probability_tp_before_sl'] is None
        assert accepted['edge_status']=='NO_EDGE_FOUND'
        assert run({'technical_trigger':False})['state']=='REJECTED'
        assert run({'zone':[entry+500,entry+600]})['state']=='REJECTED'
        assert run({'tp':entry+sign*100})['state']=='REJECTED'
        bad=run({'sl':entry+sign*100})
        assert bad['state']=='REJECTED'
        assert all(bad[k] is None for k in ('entry','sl','tp','net_rr'))
