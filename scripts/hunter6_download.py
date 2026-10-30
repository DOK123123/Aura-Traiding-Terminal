"""Resumable five-year public Bitget acquisition; no synthetic or cross-exchange fallback."""
import asyncio
import calendar
import datetime as dt
import gzip
import hashlib
import json
import sys
import time
import httpx
from pathlib import Path

from app.hunter.market import PublicMarket, SOURCE, parse_bars, validate_bars

START = int(dt.datetime(2021, 8, 1, tzinfo=dt.UTC).timestamp())
END = int(dt.datetime(2026, 10, 29, tzinfo=dt.UTC).timestamp())


async def acquire(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    market = PublicMarket()
    lock = asyncio.Lock()
    next_call = 0.0
    semaphore = asyncio.Semaphore(6)
    audits = []

    async def request(path, **params):
        nonlocal next_call
        for attempt in range(3):
            async with lock:
                delay = max(0, next_call - time.monotonic())
                if delay:
                    await asyncio.sleep(delay)
                next_call = time.monotonic() + .21  # <5 GET/s across all tasks.
            try:
                return await market.get(path, **params)
            except (ValueError, OSError, TimeoutError, httpx.RequestError) as exc:
                if attempt == 2:
                    raise ValueError(type(exc).__name__) from None
                await asyncio.sleep(2 ** attempt)

    async def month(first, end):
        async with semaphore:
            label = dt.datetime.fromtimestamp(first, dt.UTC).strftime('%Y-%m')
            file = out / (label + '.json.gz')
            if file.exists():
                rows = json.loads(gzip.decompress(file.read_bytes()))
                validate_bars(rows, 300, contiguous=False)
                if rows[0][0] < first or rows[-1][0] >= end:
                    raise ValueError('CACHE_RANGE_MISMATCH')
                return {'month': label, 'start': first, 'end': end, 'rows': len(rows), 'cached': True,
                        'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
            found, cursor, pages, duplicates = {}, end * 1000, 0, 0
            while cursor > first * 1000 and pages < 60:
                body = await request('history-candles', granularity='5m', limit=200, endTime=cursor)
                bars = parse_bars(body['data'], 300)
                pages += 1
                if not bars:
                    break
                if bars[0][0] * 1000 >= cursor:
                    raise ValueError('PAGINATION_STALLED')
                for b in bars:
                    if first <= b[0] < end:
                        if b[0] in found:
                            duplicates += 1
                            if found[b[0]] != b:
                                raise ValueError('CANDLE_CONFLICT')
                        found[b[0]] = b
                cursor = bars[0][0] * 1000
            rows = [found[t] for t in sorted(found)]
            if rows:
                validate_bars(rows, 300, contiguous=False)
                file.write_bytes(gzip.compress(json.dumps(rows, separators=(',', ':')).encode(), mtime=0))
            expected = (end - first) // 300
            audit = {'month': label, 'start': first, 'end': end, 'rows': len(rows), 'expected': expected,
                     'pages': pages, 'duplicate_identical': duplicates, 'missing': expected - len(rows),
                     'sha256': hashlib.sha256(file.read_bytes()).hexdigest() if rows else None}
            print(json.dumps(audit), flush=True)
            return audit

    try:
        windows = []
        cursor = START
        while cursor < END:
            date = dt.datetime.fromtimestamp(cursor, dt.UTC)
            end = min(END, cursor + calendar.monthrange(date.year, date.month)[1] * 86400)
            windows.append((cursor, end))
            cursor = end
        results = await asyncio.gather(*(month(a, b) for a, b in windows), return_exceptions=True)
        for window, result in zip(windows, results):
            audits.append(result if isinstance(result, dict) else {'start': window[0], 'end': window[1], 'error_type': type(result).__name__})
        funding = {}
        funding_pages = 0
        for page in range(1, 101):
            body = await request('history-fund-rate', pageSize=100, pageNo=page)
            funding_pages = page
            rows = body['data']
            if not rows:
                break
            earliest = END
            for x in rows:
                if x.get('symbol') != 'BTCUSDT':
                    raise ValueError('FUNDING_SYMBOL')
                at, rate = int(x['fundingTime']) // 1000, float(x['fundingRate'])
                if x['fundingTime'] != str(at * 1000) or not -1 < rate < 1:
                    raise ValueError('INVALID_FUNDING')
                earliest = min(earliest, at)
                if START - 86400 <= at <= END:
                    if at in funding and funding[at] != rate:
                        raise ValueError('FUNDING_CONFLICT')
                    funding[at] = rate
            if earliest < START - 86400:
                break
        values = [[t, funding[t]] for t in sorted(funding)]
        (out / 'funding.json.gz').write_bytes(gzip.compress(json.dumps(values, separators=(',', ':')).encode(), mtime=0))
        report = {'source': SOURCE, 'symbol': 'BTCUSDT', 'product': 'USDT-FUTURES', 'base_frame': '5m',
                  'requested_start': START, 'requested_end': END, 'months': audits, 'funding_pages': funding_pages,
                  'funding_rows': len(values), 'funding_sha256': hashlib.sha256((out / 'funding.json.gz').read_bytes()).hexdigest(),
                  'no_synthetic_fill': True, 'no_cross_exchange_fallback': True}
        (out / 'acquisition.json').write_text(json.dumps(report, indent=2))
        print(json.dumps({'complete': True, 'months': len(audits), 'rows': sum(r.get('rows', 0) for r in audits), 'funding': len(values)}), flush=True)
    finally:
        await market.close()


if __name__ == '__main__':
    asyncio.run(acquire(Path(sys.argv[1] if len(sys.argv) > 1 else 'data/hunter6')))
