"""Two-sided presentation of frozen rules. No eligibility or execution authority."""
from .costs import risk_reward, filled_in_zone
from .diagnostics import predicates
from .engine import FAMILIES, RULES
from .market import STEPS


def qualify_sides(scores, prepared, plans, quote, now):
    """Best = passes all gates first, then fewest failed checks, then net R/R.

    Scores describe direction, not individual strategies or profit probability.
    A missing rule plan never receives illustrative levels in this view.
    """
    lookup = {(p['strategy'], p['direction']): p for p in plans}
    for c in scores:
        choices = []
        entry = quote['ask' if c['direction'] == 'LONG' else 'bid']
        for family in FAMILIES:
            setup, trigger = predicates(prepared, len(prepared.rows)-1, family, c['direction'])
            reasons = [k for k, passed in {**setup, **trigger}.items() if not passed]
            plan = lookup.get((family, c['direction']))
            costs = None
            if plan:
                costs = risk_reward(entry, plan['sl'], plan['tp'], c['direction'],
                                    prepared.step, plan['hold_bars'], quote['ask']-quote['bid'])
                if not filled_in_zone(entry, plan['zone'], c['direction']):
                    reasons.append('ENTRY_OUTSIDE_ZONE')
                if now >= plan['valid_until']:
                    reasons.append('ENTRY_EXPIRED')
                if not costs:
                    reasons.append('INVALID_GEOMETRY_OR_COST_INPUT')
                elif costs['net_rr'] < RULES['planning']['min_net_rr']:
                    reasons.append('NET_RR_BELOW_1_5')
                if not plan['technical_trigger'] and not reasons:
                    reasons.append('TECHNICAL_TRIGGER_NOT_MET')
            else:
                reasons.append('NO_VALID_RULE_PLAN')
            choices.append((bool(reasons), len(reasons), -(costs['net_rr'] if costs else -1e9),
                            family, reasons, plan, costs))
        _, _, _, family, reasons, plan, costs = min(choices, key=lambda x: x[:4])
        if c['score'] < 50:
            reasons.append('TECHNICAL_SCORE_BELOW_50')
        # Geometry/cost validity is distinct from rule acceptance and R/R threshold.
        valid = plan is not None and costs is not None
        c.update(strategy=family, rejection_reasons=reasons, edge_status='NO_EDGE_FOUND',
                 state='REJECTED' if reasons else 'WATCH_RESEARCH',
                 technical_trigger=bool(plan and plan['technical_trigger']),
                 entry=entry if valid else None, sl=plan['sl'] if valid else None,
                 tp=plan['tp'] if valid else None, net_rr=costs['net_rr'] if valid else None,
                 costs=costs, risk_gates_passed=not reasons,
                 hold_bars=plan['hold_bars'] if plan else None,
                 assumptions='Frozen rule plan; technical score is not profit probability')
    return scores


def complete_sides(scores, error=None):
    """Always eight rows; missing/stale data cannot produce a score or a plan."""
    lookup = {(c['frame'], c['direction']): c for c in scores}
    return [lookup.get((frame, side), {
        'frame': frame, 'direction': side, 'state': 'UNKNOWN', 'score': None,
        'entry': None, 'sl': None, 'tp': None, 'net_rr': None,
        'rejection_reasons': [error or 'FRESH_CLOSED_CANDLES_AND_BID_ASK_UNAVAILABLE'],
        'edge_status': 'NO_EDGE_FOUND', 'probability_tp_before_sl': None,
        'manual_only': True, 'exchange_execution': False,
    }) for frame in STEPS for side in ('LONG', 'SHORT')]
