# Bitget Futures LIVE chart

This change adds a display-only public Bitget WebSocket feed to the main BTCUSDT
chart and an independent chart inside the Aura 4.3 panel. It supports 1m, 5m,
15m and 1h, forming-candle OHLC/base volume and visual EMA20/50.

The fixed endpoint is `wss://ws.bitget.com/v2/ws/public`, product
`USDT-FUTURES`, symbol `BTCUSDT`. Reconnect always obtains a fresh snapshot from
`https://api.bitget.com/api/v2/mix/market/candles`. There is no exchange fallback,
credential or private API. LIVE requires an accepted current-candle message;
15 seconds without one means STALE, followed by bounded reconnect/backoff.
Android background/return and page restoration close/resnapshot the connection.

The existing server feed still supplies closed candles for analysis. Provisional
bars only update the rendered series and price/EMA labels; they never mutate
`currentData` or analysis, emit a signal event, or enter PAPER execution.
H2 Observer, account APIs, strategy, risk, PAPER control, SQL, scheduler and
Cloudflare are not changed. No deployment or trading activation is included.

## Checks

```bash
python -m pytest -q
node --test tests/*.cjs
python -m scripts.verify_active43_live_browser --output-dir /new/path/browser
python -m scripts.verify_active43_live_public --output /new/path/public.json
```

The browser rehearsal uses actual Chromium and terminal HTML/scripts, synthetic
public-market fixtures, and a 393x851 mobile viewport. It checks rendering,
price/volume updates, background socket closure, return REST snapshot, timeframe
switch and preservation of closed main analytics. It is not a physical Android
or production check. The explicit public probe reads real public REST/WS only;
it never accesses accounts and is not a Render-connectivity check.

After a separately authorized deployment, check the main chart and
Owner Panel → AURA 4.3 → BTCUSDT · Bitget USDT-M Futures · LIVE.
Change intervals and observe several updates within one candle. Background the
Android Chrome tab, return, and confirm RECONNECTING → LIVE; disconnect/reconnect
network and confirm STALE → recovery. PAPER state must not be changed for this.
