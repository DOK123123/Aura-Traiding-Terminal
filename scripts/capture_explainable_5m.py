"""Bounded public GET capture; no credentials, accounts or trading endpoints."""
import argparse
import asyncio
import gzip
import hashlib
import json
from pathlib import Path
import time

from app.hunter.market import PublicMarket, SOURCE, parse_bars, validate_bars


async def capture(start: int, end: int, output: Path) -> None:
    if start < 0 or start % 300 or end % 300 or not 260*300 <= end-start <= 3000*300 or end > time.time():
        raise ValueError('INVALID_BOUNDED_CLOSED_WINDOW')
    market = PublicMarket()
    rows = {}
    cursor = end*1000
    try:
        for _ in range(16):
            body = await market.get('history-candles', granularity='5m', limit=200, endTime=cursor)
            bars = parse_bars(body['data'], 300)
            if not bars:
                break
            for row in bars:
                if start <= row[0] < end:
                    if row[0] in rows and rows[row[0]] != row:
                        raise ValueError('CONFLICTING_ARCHIVE_DUPLICATE')
                    rows[row[0]] = row
            oldest = bars[0][0]
            if oldest <= start:
                break
            if oldest*1000 >= cursor:
                raise ValueError('PAGINATION_DID_NOT_ADVANCE')
            cursor = oldest*1000
            await asyncio.sleep(.15)
        bars = [rows[t] for t in sorted(rows)]
        validate_bars(bars, 300)
        if len(bars) != (end-start)//300 or bars[0][0] != start or bars[-1][0]+300 != end:
            raise ValueError('INCOMPLETE_CAPTURE')
        payload = {'source': SOURCE, 'symbol': 'BTCUSDT', 'product': 'USDT-FUTURES',
                   'frame': '5m', 'captured_at': time.time(), 'bars': bars}
        raw = gzip.compress(json.dumps(payload, separators=(',', ':')).encode(), mtime=0)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        print(json.dumps({'bars': len(bars), 'first': start, 'last_close': end, 'sha256': hashlib.sha256(raw).hexdigest()}))
    finally:
        await market.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--end', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(capture(args.start, args.end, args.output))
