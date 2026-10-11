# Bybit Demo Trading — strictly read-only

Aura uses the official V5 Demo REST host `https://api-demo.bybit.com` only.
This is **mainnet Demo Trading**, an isolated virtual-funds account, not the
real-money account or `api-testnet.bybit.com`. No host override, production
fallback, order execution, amendments, cancellations, transfers, withdrawals,
automatic trading or Demo top-up requests exist in this integration.

## Render setup

1. Log in to Bybit's official website and switch to **Demo Trading**.
2. While inside Demo Trading, open the avatar → **API** and generate a
   system-generated HMAC key. Select read-only access and permissions for
   wallet/account, orders and execution history. Aura does not need write access.
   Do not use a real-money key or a key created on the Bybit Testnet website.
3. Keep credentials in a password manager; never send them to chat or GitHub.
4. Render → Aura Web Service → **Environment**:

   | Variable | Value |
   | --- | --- |
   | `BYBIT_DEMO_API_KEY` | Key from Demo Trading |
   | `BYBIT_DEMO_API_SECRET` | Corresponding HMAC Secret |
   | `AURA_TESTNET_VIEW_PASSWORD` | Existing separate owner-view password, 12+ characters (24+ recommended) |

   The legacy owner-password name is deliberately reused; it is not an exchange
   credential. Binance variables are optional and never used by Bybit.
5. Save/redeploy; start remains `python start_web.py`. No new dependencies.
6. Open Aura using HTTPS on the phone. In **BYBIT DEMO / READ ONLY**, click the
   login link, use username **aura** and the owner-view password.
7. Select category and symbol (Spot/BTCUSDT initially). Read wallet balances,
   open orders and request history. For inverse/options choose a symbol valid
   in that category; a missing/unsupported category is an explicit safe error.

Bybit documents restrictions for US/Mainland-China API IPs. Switching providers
does not guarantee that the existing Render region works. HTTP 403 may also
mean an IP rate ban; it is not necessarily a bad key. Consult Bybit's permitted
regions and Render's outbound IP list; do not bypass restrictions, disable TLS
or substitute production hosts. Test actual service connectivity after redeploy.

## Data scope and semantics

- `GET /api/bybit-demo/account?category=spot&symbol=BTCUSDT`: UNIFIED wallet
  across all returned assets, USD account totals, selected category/symbol's
  open orders (`openOnly=0`). Demo/open-order status is not account WebSocket.
- `GET /api/bybit-demo/history?category=spot&symbol=BTCUSDT`: order history and
  executions for the selected scope in a fixed seven-day window. Four pages
  of 50 per list maximum (200 each); flags indicate more pages. Demo order
  retention and cancelled/rejected order availability follow Bybit limitations.
- `GET /api/bybit-demo/login`: owner login and redirect to the terminal.
- API responses carry `provider=BYBIT_DEMO`, `demo=true`, `virtual_funds=true`,
  `real_money=false`, `read_only=true` and selected scope. The frontend rejects
  a Connected response with mismatched identity/scope.

Wallet balance, equity and available account margin are **not** interchangeable.
`locked` is a Spot-order field, not all derivatives margin. Amounts remain exact
decimal strings; negative equity or fee rebates are retained. Missing fields
are null/—, never fake zero. Deprecated `free`/`availableToWithdraw` are ignored.
`available_assets` lists positive wallet balances, not guaranteed spendable
funds. Coin wallet includes liabilities/borrow semantics; spotBorrow is shown.
Totals are USD, not a fabricated USDT conversion using the terminal chart.
Executions show their type and fee currency when supplied; no fee asset is guessed.

## Authentication, failure and freshness

Private requests use `X-BAPI-API-KEY`, `X-BAPI-TIMESTAMP`, `X-BAPI-RECV-WINDOW=5000`,
`X-BAPI-SIGN` (HMAC-SHA256 hex) and sign type 2. Signature input is timestamp +
API key + recvWindow + the exact URL-encoded GET query. No GET JSON body.
`GET /v5/market/time` is unsigned; `timeNano` synchronizes milliseconds every
five minutes. Clock errors trigger one resync/retry only.

The only allowed private paths are `/v5/account/wallet-balance`,
`/v5/order/realtime`, `/v5/order/history`, `/v5/execution/list` (GET only).
TLS stays enabled, redirects are never followed. Keys load only from server ENV;
owner authentication is mandatory when configured. Missing keys return
**Not configured** without exchange traffic; market/chart work as before.
Configured keys without a valid owner password fail closed. Browser/API/cache
responses never contain keys, secrets, signatures, upstream bodies or headers.

Safe diagnostics contain only the allowlisted path, HTTP status, numeric retCode
and fixed network/timeout types. Distinct errors cover key/domain mismatch,
signature, permission, key expiry, IP whitelist, clock, region/account mode,
HTTP/API/server failures and malformed responses. Raw `retMsg`, exceptions,
authenticated request URLs and headers are never logged/returned. Transport
debug output is disabled; logger and handler filters block credential echoes
and later-created child-logger tracebacks.

HTTP 418/429 and retCode 10006 honor Retry-After and V5 limit-reset time.
HTTP 403 backs off at least ten minutes, because it may be an IP rate ban.
Exhausted successful limit headers delay the next request. Cooldown is shared
across scopes, request timeout is eight seconds, entire snapshot 25 seconds.
Polling is once per minute; bounded process cache TTL is 60 seconds, no stale
balance on failed reads. UI hides snapshots older than 90 seconds and cancels
requests/history on scope changes or page exit. Restart/redeploy clears cache;
multiple workers need shared rate-limit control. Keep the existing one worker.

Binance remains separate and unchanged under `/api/testnet/*`. Bybit never calls
it as fallback; `static/testnet.js` is retained but not loaded by the primary UI.
Public Binance market-data pipelines, charts, strategy and backtest are unchanged.

## Verification

Run `python -m pytest -q` and all three Node suites:
`tests/test_frontend_reliability.cjs`, `tests/test_testnet_frontend.cjs`,
`tests/test_bybit_demo_frontend.cjs`. All exchange traffic uses MockTransport
and clearly dummy credentials, no order writes. Check syntax/imports, credential
scan, fixed host/GET-only allowlist and unchanged Binance implementation.
Offline checks do not establish live connectivity or the permissions of your key.

## Official sources (checked 2026-10-11)

- [Bybit Demo Trading](https://bybit-exchange.github.io/docs/v5/demo)
- [V5 authentication and region restrictions](https://bybit-exchange.github.io/docs/v5/guide)
- [UNIFIED wallet balance](https://bybit-exchange.github.io/docs/v5/account/wallet-balance)
- [Open orders](https://bybit-exchange.github.io/docs/v5/order/open-order)
- [Order history](https://bybit-exchange.github.io/docs/v5/order/order-list)
- [Execution history](https://bybit-exchange.github.io/docs/v5/order/execution)
- [Server time](https://bybit-exchange.github.io/docs/v5/market/time)
- [Error codes](https://bybit-exchange.github.io/docs/v5/error)
- [Rate limits](https://bybit-exchange.github.io/docs/v5/rate-limit)
- [Render outbound IPs](https://render.com/docs/outbound-ip-addresses)
