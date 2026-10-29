"""Bounded public Bitget capture for the read-only forward observer; no orders."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import time
import httpx
from websockets.sync.client import connect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=20, choices=range(5, 61))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    def history(tf):
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.get('https://api.bitget.com/api/v2/mix/market/candles', params={
                'symbol': 'BTCUSDT', 'productType': 'USDT-FUTURES', 'granularity': tf, 'limit': 201})
            response.raise_for_status()
            return {'kind': 'history', 'tf': {'1H': '1h', '4H': '4h'}.get(tf, tf),
                    'received_at': time.time(), 'body': response.json()}
    with ThreadPoolExecutor(max_workers=5) as pool:
        records.extend(pool.map(history, ('1m', '5m', '15m', '1H', '4H')))
    records.append({'kind': 'start', 'received_at': time.time()})
    with connect('wss://ws.bitget.com/v2/ws/public', open_timeout=15, close_timeout=2) as ws:
        ws.send(json.dumps({'op': 'subscribe', 'args': [{'instType': 'USDT-FUTURES',
            'instId': 'BTCUSDT', 'channel': channel} for channel in
            ('ticker', 'candle1m', 'candle5m', 'candle15m', 'candle1H', 'candle4H')]}))
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            try:
                raw = ws.recv(timeout=2)
            except TimeoutError:
                continue
            if raw == 'pong':
                continue
            records.append({'kind': 'message', 'received_at': time.time(), 'body': json.loads(raw)})
    records.append({'kind': 'end', 'received_at': time.time()})
    capture = args.output / 'capture.json'
    capture.write_text(json.dumps(records))
    subprocess.run(['node', 'scripts/observe_manual_strategies.cjs', str(capture),
                    str(args.output / 'report.json')], check=True)


if __name__ == '__main__':
    main()
