"""Immutable single-source archives and exact UTC aggregation; never fill missing bars."""
import gzip
import hashlib
import json
from pathlib import Path

from app.hunter.market import SOURCE, validate_bars


def load(folder='data/hunter6'):
    folder = Path(folder)
    manifest = json.loads((folder/'acquisition.json').read_text())
    if manifest['source'] != SOURCE:
        raise ValueError('UNREGISTERED_SOURCE')
    rows = []
    for month in sorted(manifest['months'], key=lambda x: x['start']):
        if 'error_type' in month or not month.get('sha256'):
            raise ValueError('INCOMPLETE_ACQUISITION')
        file = folder/(month['month']+'.json.gz')
        if hashlib.sha256(file.read_bytes()).hexdigest() != month['sha256']:
            raise ValueError('ARCHIVE_HASH_MISMATCH')
        values = json.loads(gzip.decompress(file.read_bytes()))
        validate_bars(values, 300, contiguous=False)
        if any(not month['start'] <= b[0] < month['end'] for b in values):
            raise ValueError('ARCHIVE_TIME_MISMATCH')
        rows.extend(values)
    validate_bars(rows, 300, contiguous=False)
    raw = (folder/'funding.json.gz').read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['funding_sha256']:
        raise ValueError('FUNDING_HASH_MISMATCH')
    funding = json.loads(gzip.decompress(raw))
    if any(type(t) is not int or not -1 < rate < 1 for t, rate in funding) or any(b[0] <= a[0] for a, b in zip(funding, funding[1:])):
        raise ValueError('INVALID_FUNDING_ARCHIVE')
    return rows, funding, manifest


def aggregate(rows, step):
    validate_bars(rows, 300, contiguous=False)
    if step % 300 or step < 300:
        raise ValueError('INVALID_AGGREGATION')
    out, group, at = [], [], None
    for b in rows:
        bucket = b[0]//step*step
        if at is not None and bucket != at:
            if len(group) == step//300 and group[0][0] == at and group[-1][0] == at+step-300:
                out.append([at, group[0][1], max(x[2] for x in group), min(x[3] for x in group), group[-1][4], sum(x[5] for x in group)])
            group = []
        at = bucket
        group.append(b)
    if group and len(group) == step//300 and group[0][0] == at and group[-1][0] == at+step-300:
        out.append([at, group[0][1], max(x[2] for x in group), min(x[3] for x in group), group[-1][4], sum(x[5] for x in group)])
    return out


def audit(rows, funding, manifest):
    gaps = [[a[0]+300, b[0], (b[0]-a[0])//300-1] for a, b in zip(rows, rows[1:]) if b[0]-a[0] != 300]
    rate_gaps = [[a[0], b[0]] for a, b in zip(funding, funding[1:]) if b[0]-a[0] > 8*3600]
    return {'source': SOURCE, 'requested_start': manifest['requested_start'], 'requested_end': manifest['requested_end'],
            'actual_start': rows[0][0], 'actual_end_exclusive': rows[-1][0]+300, 'base_candles': len(rows),
            'missing_candles': sum(x[2] for x in gaps), 'gaps': gaps, 'duplicate_or_conflicting_archived_rows': 0,
            'funding_rows': len(funding), 'funding_gaps_over_8h': rate_gaps,
            'funding_first': funding[0][0] if funding else None, 'funding_last': funding[-1][0] if funding else None,
            'funding_coverage_complete': bool(funding and funding[0][0] <= rows[0][0] and funding[-1][0] >= rows[-1][0]-8*3600 and not rate_gaps),
            'frame_candles': {name: len(aggregate(rows, step)) for name, step in [('5m',300),('15m',900),('1h',3600),('4h',14400)]},
            'gap_policy': 'NO_FILL; DROP_INCOMPLETE_AGGREGATES; RESET_250_BAR_WARMUP; OPEN_HYPOTHESIS_UNKNOWN_ON_GAP'}
