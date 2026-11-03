"""Reproducible, fixed-rule comparison on preserved real Bitget OHLCV.

Research calculation only. No order/virtual-account calls. Archive was used by
prior research: this is NOT independent out-of-sample statistical qualification.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from app.hunter.costs import risk_reward, exit_fill
from app.hunter.market import SOURCE, validate_bars
from app.manual_preview.explainable import evaluate, MODEL_HASH, VERSION

ARCHIVE = Path('research/strategy_engine/bitget-2026-07-10-15m.json.gz')


def bars_for(base, step):
    groups = defaultdict(list)
    for row in base:
        groups[row['time']//step*step].append(row)
    return [[at, v[0]['open'], max(x['high'] for x in v), min(x['low'] for x in v), v[-1]['close'], sum(x['volume'] for x in v)]
            for at, v in groups.items() if len(v) == step//900]


def outcome(plan, bars, step):
    i = plan['index']
    side = plan['direction']; sign = 1 if side == 'LONG' else -1
    hold = plan['hold_bars']
    if i+hold >= len(bars):
        return {'outcome': 'UNKNOWN', 'reason': 'RIGHT_CENSORED'}
    # Only now, after the decision, read the next actual open. Quote is a model.
    entry = bars[i+1][1]*(1+sign*.0001)
    if plan.get('zone') and not plan['zone'][0] <= entry*(1+sign*.0005) <= plan['zone'][1]:
        return {'outcome': 'NO_FILL', 'reason': 'NEXT_OPEN_OUTSIDE_ZONE'}
    costs = risk_reward(entry, plan['sl'], plan['tp'], side, step, hold, entry*.0002)
    if costs is None or costs['net_rr'] < 1.5:
        return {'outcome': 'NO_FILL', 'reason': 'NEXT_OPEN_INVALID_NET_RR'}
    exit_price = None; kind = 'TIMEOUT'
    for row in bars[i+1:i+hold+1]:
        # OHLC proxy to exit-side quotes, conservative gaps and SL-first ties.
        o, h, l, c = (x*(1-sign*.0001) for x in row[1:5])
        if sign*(o-plan['sl']) <= 0:
            exit_price = o; kind = 'SL'; break
        if (l <= plan['sl'] if sign == 1 else h >= plan['sl']):
            exit_price = plan['sl']; kind = 'SL'; break
        if (h >= plan['tp'] if sign == 1 else l <= plan['tp']):
            exit_price = plan['tp']; kind = 'TP'; break
    if exit_price is None:
        exit_price = bars[i+hold][4]*(1-sign*.0001)
    filled = exit_fill(exit_price, side)
    e = costs['entry_fill']
    pnl = sign*(filled-e)-.001*(e+filled)-costs['funding_reserve']
    return {'outcome': kind, 'net_r': pnl/costs['net_loss'], 'net_usdt_per_btc': pnl}


def summary(results):
    closed = [v for v in results if 'net_r' in v]
    win = sum(max(0, v['net_r']) for v in closed)
    loss = -sum(min(0, v['net_r']) for v in closed)
    return {'count': len(results), 'closed': len(closed), 'outcomes': dict(Counter(v['outcome'] for v in results)),
            'mean_net_r': sum(v['net_r'] for v in closed)/len(closed) if closed else None,
            'profit_factor_net_r': win/loss if loss else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = json.load(gzip.open(ARCHIVE))
    old = json.loads(args.baseline.read_text())
    report = {'scope': 'OFFLINE_RESEARCH_NO_ORDERS', 'verdict': 'NO_EDGE_FOUND', 'version': VERSION,
              'model_sha256': MODEL_HASH, 'archive_sha256': hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
              'source': 'BITGET_SAVED_REAL_ARCHIVE_2026_07_01_TO_10_29',
              'historical_bid_ask': False, 'historical_funding': False,
              'assumptions': {'fee_bps_per_side': 10, 'slippage_bps_per_side': 5, 'full_spread_bps': 2,
                              'funding_reserve_bps_per_8h': 1, 'entry': 'NEXT_OPEN_AFTER_DECISION',
                              'tie': 'SL_FIRST', 'gaps': 'ADVERSE_STOP_OPEN', 'sizing': 'INDEPENDENT_1R_OBSERVATIONS_NOT_PORTFOLIO'},
              'limitations': ['Previously researched archive, not independent OOS', 'Overlapping hypotheses, no portfolio return claim',
                              'Native 5m is analyzed separately in native5m.json; never fabricated from 15m',
                              '1h/4h aggregated from complete 15m archive, not live native seeding equivalence',
                              'Baseline hold=24 bars vs new hold<=4h; comparison includes intentional horizon change',
                              'No parameter search or independent statistical qualification'], 'frames': {}, 'examples': {}}
    for frame, step in [('15m', 900), ('1h', 3600), ('4h', 14400)]:
        bars = bars_for(base, step); validate_bars(bars, step)
        states = Counter(); rejected = Counter(); signals = []; technical = Counter()
        for i in range(259, len(bars)):
            now = bars[i][0]+step; mid = bars[i][4]
            q = dict(source=SOURCE, bid=mid*.9999, ask=mid*1.0001, last=mid, time=now, received_at=now)
            for row in evaluate(bars[i-259:i+1], frame, q, now):
                states[row['state']] += 1; rejected.update(row['rejection'])
                if all(x['passed'] for x in row['checks']):
                    technical[row['strategy']+'|'+row['direction']] += 1
                key = row['strategy']+'|'+row['direction']
                if row['state'] != 'WATCH':
                    if row['stop_explanation'] and key+'|REJECTED' not in report['examples']:
                        report['examples'][key+'|REJECTED'] = row
                    continue
                if key+'|WATCH' not in report['examples']:
                    report['examples'][key+'|WATCH'] = row
                a = row['indicators']['atr']
                signals.append({'index': i, 'strategy': row['strategy'], 'direction': row['direction'],
                                'sl': row['sl'], 'tp': row['tp'], 'hold_bars': row['horizon']['hold_bars'],
                                'zone': [mid-.25*a, mid+.25*a]})
        frame_data = {'bars': len(bars), 'first_utc': datetime.fromtimestamp(bars[0][0], timezone.utc).isoformat(),
                      'last_close_utc': datetime.fromtimestamp(bars[-1][0]+step, timezone.utc).isoformat(),
                      'states_after': dict(states), 'rejection_reasons_after': dict(rejected), 'technical_setups_before_risk_gates': dict(technical)}
        for name, plans in [('before', old[frame]), ('after', signals)]:
            results = [dict(strategy=p['strategy'], direction=p['direction'], **outcome(p, bars, step)) for p in plans]
            frame_data[name] = summary(results)
            frame_data[name]['groups'] = {s+'|'+d: summary([x for x in results if x['strategy']==s and x['direction']==d])
                                          for s, d in sorted({(x['strategy'], x['direction']) for x in results})}
        report['frames'][frame] = frame_data
        print(frame, json.dumps({'before': frame_data['before']['count'], 'after': frame_data['after']['count']}), flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'replay.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
