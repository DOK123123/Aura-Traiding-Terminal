"""Native 5m research supplement. Frozen explainable rules, no parameter search."""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from app.hunter.market import SOURCE, validate_bars
from app.manual_preview.explainable import evaluate, MODEL_HASH
from scripts.replay_explainable import outcome, summary

ARCHIVE = Path('research/strategy_engine/bitget-native-5m-2026-11-02.json.gz')


def replay() -> dict:
    payload = json.load(gzip.open(ARCHIVE))
    if payload['source'] != SOURCE or payload['frame'] != '5m' or payload['product'] != 'USDT-FUTURES':
        raise ValueError('INVALID_NATIVE_ARCHIVE_IDENTITY')
    bars = payload['bars']; validate_bars(bars, 300)
    states = Counter(); reasons = Counter(); technical = Counter(); results = []; examples = {}
    for i in range(259, len(bars)):
        now = bars[i][0]+300; mid = bars[i][4]
        q = dict(source=SOURCE, bid=mid*.9999, ask=mid*1.0001, last=mid, time=now, received_at=now)
        for row in evaluate(bars[i-259:i+1], '5m', q, now):
            states[row['direction']+'|'+row['state']] += 1
            reasons.update(row['rejection'])
            key = row['strategy']+'|'+row['direction']
            if all(c['passed'] for c in row['checks']):
                technical[key] += 1
                examples.setdefault(key, row)
            if row['state'] != 'WATCH':
                continue
            atr = row['indicators']['atr']
            plan = dict(index=i, direction=row['direction'], sl=row['sl'], tp=row['tp'],
                        hold_bars=row['horizon']['hold_bars'], zone=[mid-.25*atr, mid+.25*atr])
            results.append(dict(strategy=row['strategy'], direction=row['direction'], **outcome(plan, bars, 300)))
    return {'scope': 'REAL_NATIVE_5M_OFFLINE_RESEARCH_NO_ORDERS', 'verdict': 'NO_EDGE_FOUND',
            'model_sha256': MODEL_HASH, 'archive_sha256': hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
            'bars': len(bars), 'first_utc': datetime.fromtimestamp(bars[0][0], timezone.utc).isoformat(),
            'last_close_utc': datetime.fromtimestamp(bars[-1][0]+300, timezone.utc).isoformat(),
            'source': SOURCE, 'historical_bid_ask': False, 'historical_funding': False,
            'native_not_aggregated': True, 'baseline_5m': 'NOT_APPLICABLE_OLD_INDEPENDENT_PANEL_SUPPORTED_15m_1h_4h',
            'costs': 'Same modeled 10bps fee/side, 5bps slip/side, 2bps spread, 1bps funding/8h as main replay',
            'entry': 'NEXT_OPEN_AFTER_CLOSED_DECISION; SL_FIRST; ADVERSE_STOP_GAPS',
            'independent_oos': False, 'no_parameter_search': True, 'states': dict(states),
            'rejection_reasons': dict(reasons), 'technical_setups_before_risk': dict(technical),
            'after': summary(results), 'examples': examples}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = replay()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: report[k] for k in ('bars', 'first_utc', 'last_close_utc', 'technical_setups_before_risk', 'after')}))
