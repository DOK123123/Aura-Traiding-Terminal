"""Network smoke test, independent of a running web server."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
import argparse
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from app.indicators import analyze
from app.main import PROVIDERS
from app.models import INTERVALS
from app.gold import TradingViewGoldProvider


async def main(symbol=None, output=None, gold_fallback=False):
    failed = False
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "checks": []}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for instrument, provider in PROVIDERS.items():
            if symbol and instrument != symbol:
                continue
            if gold_fallback:
                if instrument != 'XAUUSD':
                    continue
                provider = TradingViewGoldProvider()
            for timeframe in INTERVALS:
                for count in (500, 2000):
                    try:
                        async with asyncio.timeout(100):
                            candles = await provider.fetch(client, timeframe, count)
                        assert len(candles) == count, f'Expected {count}, got {len(candles)}'
                        assert all(a.time < b.time for a, b in zip(candles, candles[1:]))
                        result = analyze(candles)
                        assert result['signal_up'] + result['signal_down'] == 100
                        check = {"symbol": instrument, "timeframe": timeframe, "requested": count,
                                 "received": len(candles), "status": "OK",
                                 "source": getattr(candles, 'source', provider.name),
                                 "fallback": getattr(candles, 'fallback', False),
                                 "fallback_reason": getattr(candles, 'reason', None),
                                 "last_close": candles[-1].close,
                                 "first_open_at": datetime.fromtimestamp(candles[0].time, timezone.utc).isoformat(),
                                 "last_closed_at": datetime.fromtimestamp(candles[-1].time + INTERVALS[timeframe], timezone.utc).isoformat()}
                        report['checks'].append(check)
                        print(json.dumps(check, ensure_ascii=True), flush=True)
                    except Exception as exc:
                        failed = True
                        check = {"symbol": instrument, "timeframe": timeframe, "requested": count,
                                 "status": "FAIL", "error": repr(exc)}
                        report['checks'].append(check)
                        print(json.dumps(check, ensure_ascii=True), flush=True)
    if output:
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return int(failed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', choices=list(PROVIDERS))
    parser.add_argument('--output', help='Save verification summary as JSON; no candle data is stored')
    parser.add_argument('--gold-fallback', action='store_true', help='Check real OANDA history directly for all eight gold combinations')
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.symbol, args.output, args.gold_fallback)))
