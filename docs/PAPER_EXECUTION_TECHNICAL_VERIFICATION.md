# PAPER EXECUTION TECHNICAL VERIFICATION

TECHNICAL EXECUTION: **PASS** — 12/12 scenarios, 16 subcases, 15 committed OPEN and 15 CLOSE.

LIVE AUTONOMOUS EXECUTION: **WAITING_FOR_REAL_SIGNAL**.

This report proves isolated technical execution, not operation on Render. Production was not observed or contacted. This status does not assert that production is healthy, waiting, or free of errors. No isolated test can set LIVE VERIFIED.

## Scope and safety

Base: `main` at `c50fd0bb2402bd261089142c96d4e9981f4594ab`.
Only a CLI harness, independent oracle, regression tests and these reports are added. No runtime routes, buttons, dependencies, strategy, risk parameters, scheduler cadence, SQL schema, credentials, portfolio or existing monitor evidence are modified. Nothing was merged or deployed.

Each subcase creates its own new temporary SQLite account with 10,000 virtual units. No configurable database path is accepted. The production SQLiteStore, Service, strategy, execution engine and monitor are used unchanged. Synthetic, fixed OHLC candles and preconstructed synthetic market contexts are exclusively test inputs; they are not historical data, real signals, or evidence of strategy performance. Production indicator ingestion and natural signal quality are outside this harness.

The process blocks IPv4/IPv6 socket connect/connect_ex and construction of SupabaseStore. Render provenance is cleared. The only scheduler token is explicitly dummy. Scheduler requests use an in-process ASGI adapter, with no external HTTP. Unix IPC is allowed for the fresh-interpreter restart test. These guards are local test safeguards, not a separate network sandbox. The harness never calls production configuration factories.

## Audit and existing coverage

| Component / production path | Existing coverage | Additional evidence here |
|---|---|---|
| `app/automated/strategy.py` → `service.py` snapshot/decision | `test_auto42.py`: deterministic LONG/SHORT, closed multi-timeframe data, malformed/stale data, alignment, causality | Unchanged strategy consumes synthetic context; pending signal fills at next available candle open |
| `app/automated/engine.py`: advance/open_virtual/protective/close_virtual/mark | `test_auto42.py`: sizing, fee-inclusive risk, daily/drawdown gates, one position, ambiguous candles, gaps, next open, missed candles | Independent Fraction arithmetic checks all completed cycles and POSITION_UPDATE liquidation equity |
| `app/automated/storage.py`: SQLiteStore.commit | Existing revision CAS, duplicates, rollback and concurrent instance tests | Failure injected AFTER event insert and account update; complete rollback of account/events/watermark, then same-candle retry |
| Restart and idempotency | Existing reconstructed-object/pending/risk recovery tests | Spawned fresh Python interpreter restores exact open position; duplicate tick changes nothing |
| `scripts/auto42_scheduler.py` → authenticated `app/automated/api.py` tick | Existing offline scheduler/authentication tests | Actual scheduler client called three times through local ASGI; no-token 401; exactly one OPEN |
| `app/automated/live_monitor.py` | `test_live_paper_monitor.py`: owner auth, read-only access even with crossed target, provenance, errors, net PnL, duplicate events | All isolated events remain non-production; no live verification even after complete cycles |
| SupabaseStore + `scripts/auto42_schema.sql` | Existing mocked RPC/contract and error-handling tests; static transaction/CAS review | **No live Supabase calls. Live RPC atomicity and durability NOT TESTED** |
| Legacy `app/paper/`, provider diagnostics and UI | Full Python and Node regression suites | No legacy/runtime/frontend changes |

The normal service flow is closed snapshot → unchanged strategy → risk-gated pending entry → next candle open → atomic state/journal/watermark commit → liquidation mark → protective SL/TP → fees/net PnL → atomic commit. Browser UI is not called by the harness or scheduler. This supports architectural independence from a browser; it does not establish actual Render uptime with a closed browser.

## Scenario results

| # | Scenario | Result | OPEN / CLOSE |
|---|---|---|---|
| 1 | LONG → TAKE PROFIT | PASS | 1 / 1 |
| 2 | LONG → STOP LOSS | PASS | 1 / 1 |
| 3 | SHORT → TAKE PROFIT | PASS | 1 / 1 |
| 4 | SHORT → STOP LOSS | PASS | 1 / 1 |
| 5 | Simultaneous SL/TP; SL first | PASS | 2 / 2 |
| 6 | Fresh-process recovery with open position | PASS | 1 / 1 |
| 7 | Same candle in next scheduler slot | PASS | 1 / 1 |
| 8 | Repeated real scheduler client via local ASGI | PASS | 1 / 1 |
| 9 | Database failure after inserts/account update | PASS | 0 / 0 |
| 10 | Recovery/retry after failed database transaction | PASS | 1 / 1 |
| 11 | Competing controllers forced same revision | PASS | 1 / 1 |
| 12 | Independent math; adverse stop and conservative TP gaps | PASS | 4 / 4 |

Each subcase starts independently at 10,000. Prices below are actual fills after slippage. `—` means no committed trade. All financial values and raw prices/times, risk, source-fixture and code hashes are in [the machine-readable report](PAPER_EXECUTION_TECHNICAL_VERIFICATION.json).

| Subcase | Direction | Entry | Size BTC | SL | TP | Exit |
|---|---|---:|---:|---:|---:|---:|
| LONG_TP | LONG | 100.0500 | 17.881082742475 | 97.5 | 105.0 | 104.94750 |
| LONG_SL | LONG | 100.0500 | 17.881082742475 | 97.5 | 105.0 | 97.45125 |
| SHORT_TP | SHORT | 99.9500 | 17.833251066762 | 102.5 | 95.0 | 95.04750 |
| SHORT_SL | SHORT | 99.9500 | 17.833251066762 | 102.5 | 95.0 | 102.55125 |
| LONG_BOTH | LONG | 100.0500 | 17.881082742475 | 97.5 | 105.0 | 97.45125 |
| SHORT_BOTH | SHORT | 99.9500 | 17.833251066762 | 102.5 | 95.0 | 102.55125 |
| RESTART | LONG | 100.0500 | 17.881082742475 | 97.5 | 105.0 | 104.94750 |
| SAME_CANDLE | LONG | 100.0500 | 17.881082742475 | 97.5 | 105.0 | 104.94750 |
| SCHEDULER | LONG | 100.0500 | 17.881082742475 | 97.5 | 105.0 | 104.94750 |
| ROLLBACK | LONG | — | — | 97.5 | 105.0 | — |
| RECOVERY | LONG | 100.0500 | 17.881082742475 | 97.5 | 105.0 | 104.94750 |
| RACE | SHORT | 99.9500 | 17.833251066762 | 102.5 | 95.0 | 102.55125 |
| LONG_STOP_GAP | LONG | 100.0500 | 17.881082742475 | 97.5 | 105.0 | 95.45225 |
| LONG_TP_GAP | LONG | 100.0500 | 17.881082742475 | 97.5 | 105.0 | 104.94750 |
| SHORT_STOP_GAP | SHORT | 99.9500 | 17.833251066762 | 102.5 | 95.0 | 104.55225 |
| SHORT_TP_GAP | SHORT | 99.9500 | 17.833251066762 | 102.5 | 95.0 | 95.04750 |

| Subcase | Entry fee | Exit fee | Total fees | Slippage cost¹ | Net PnL | Final balance | OPEN/CLOSE |
|---|---:|---:|---:|---:|---:|---:|---|
| LONG_TP | 1.78900233 | 1.87657494 | 3.66557727 | 1.83281098 | 83.90702546 | 10083.90702546 | 1/1 |
| LONG_SL | 1.78900233 | 1.74253387 | 3.53153620 | 1.76575692 | -49.99999998 | 9950.00000002 | 1/1 |
| SHORT_TP | 1.78243345 | 1.69500594 | 3.47743939 | 1.73874198 | 83.95007396 | 10083.95007396 | 1/1 |
| SHORT_SL | 1.78243345 | 1.82882219 | 3.61125564 | 1.80561667 | -49.99999998 | 9950.00000002 | 1/1 |
| LONG_BOTH | 1.78900233 | 1.74253387 | 3.53153620 | 1.76575692 | -49.99999998 | 9950.00000002 | 1/1 |
| SHORT_BOTH | 1.78243345 | 1.82882219 | 3.61125564 | 1.80561667 | -49.99999998 | 9950.00000002 | 1/1 |
| RESTART | 1.78900233 | 1.87657494 | 3.66557727 | 1.83281098 | 83.90702546 | 10083.90702546 | 1/1 |
| SAME_CANDLE | 1.78900233 | 1.87657494 | 3.66557727 | 1.83281098 | 83.90702546 | 10083.90702546 | 1/1 |
| SCHEDULER | 1.78900233 | 1.87657494 | 3.66557727 | 1.83281098 | 83.90702546 | 10083.90702546 | 1/1 |
| ROLLBACK | — | — | 0 | 0 | 0 | 10000 | 0/0 |
| RECOVERY | 1.78900233 | 1.87657494 | 3.66557727 | 1.83281098 | 83.90702546 | 10083.90702546 | 1/1 |
| RACE | 1.78243345 | 1.82882219 | 3.61125564 | 1.80561667 | -49.99999998 | 9950.00000002 | 1/1 |
| LONG_STOP_GAP | 1.78900233 | 1.70678959 | 3.49579192 | 1.74787584 | -85.70854010 | 9914.29145990 | 1/1 |
| LONG_TP_GAP | 1.78900233 | 1.87657494 | 3.66557727 | 1.83281098 | 83.90702546 | 10083.90702546 | 1/1 |
| SHORT_STOP_GAP | 1.78243345 | 1.86450653 | 3.64693998 | 1.82344992 | -85.72001970 | 9914.27998030 | 1/1 |
| SHORT_TP_GAP | 1.78243345 | 1.69500594 | 3.47743939 | 1.73874198 | 83.95007396 | 10083.95007396 | 1/1 |

¹ Slippage is already incorporated into fill prices and PnL; it is not subtracted a second time. Entry and exit fee rates are 0.1% each; slippage is 0.05% each side, matching unchanged production constants.

## Independent mathematics and failure guarantees

`scripts/paper_e2e_oracle.py` imports no engine/risk/fill helpers. It uses exact rational arithmetic, separately implements 8-decimal HALF_EVEN/CEILING rounding and 12-decimal quantity flooring, fee-inclusive sizing, the production rounding reserves, direction-specific fills, SL-first ambiguous execution, conservative TP gaps and adverse SL gaps. It checks position/trade identity, raw entry against the actual next candle, exit timestamp, entry/exit fees, gross/net PnL, risk, liquidation marks and final balance. Mutation tests reject incorrect size, exit price, exit fee and realized PnL. Shared specifications/constants are intentional; this is independent arithmetic, not independent market validation.

For the storage fault, a temporary SQLite trigger runs after the account update. Its callback sees the inserted OPEN and incremented revision within the uncommitted transaction and then raises an error. After rollback, exact account, revision, watermark and journal match their prior values; there is no phantom OPEN. A retry on that same candle commits one entry and later one exit. This proves atomicity for the tested production SQLite backend and this failure point, not all crash/power-loss/network-acknowledgement cases or live Supabase RPC.

Two Service instances are forced to reach commit with the same expected revision. One wins, one is a duplicate; only one trade is recorded. Repeated close ticks are exact journal/account no-ops. A new scheduler slot on the same candle records a heartbeat without financial changes. A real spawned interpreter reopens the temporary database, restores the exact position and safely reprocesses a duplicate tick. Render/Supabase restart behavior still needs live observation.

## Findings and review

No execution defect was demonstrated in the tested paths. No production correction is proposed or applied. The defect encountered while writing an oracle unit test was an incomplete test setup: calling protective directly omitted the mark step performed by production advance. The test now follows that sequence; runtime code is unchanged.

**Gap limitation:** ordinary SL losses are approximately 50 USDT (0.5% of the initial account, fees included), but adverse stop gaps produce losses of 85.70854010 LONG and 85.72001970 SHORT. A stop is not a guaranteed execution price. These are expected consequences of the unchanged gap model, not a claim that actual loss is always capped at 0.5%. TP gaps use the target conservatively. Simultaneous intrabar SL/TP assumes SL first.

Separate code-review and security-review passes inspected the new files against `docs/ecc/TRADING_REVIEW.md`: no runtime imports of the harness, new public endpoint, exchange writer, production store selection or credential output. Output filename/schema/symlink checks prevent accidental replacement of unrelated reports. Repository runtime, scheduler, SQL and frontend diff against base is empty. No critical/high findings identified within this change. Remaining risks are the unobserved live backend, network/crash failure modes beyond the injected fault, and the limits of fixed OHLC execution simulation.

## Reproduction and test results

From the repository root with requirements installed:

```bash
python -m scripts.verify_paper_e2e --output /tmp/aura-check/PAPER_EXECUTION_TECHNICAL_VERIFICATION.json
python -m pytest -q
```

The harness is CLI-only; do not add it to Render startup or cron. It creates and removes its own temporary databases. `--sandbox-poll` optionally selects the existing test-only event-loop accommodation for this managed environment. No runtime event-loop change is made.

Final validation: **1208 Python tests passed** in 84.24s, including 10 new harness/oracle/guard tests. One existing dependency warning: Starlette refers to the deprecated `anyio.abc.BlockingPortal` alias. **All 16 `tests/*.cjs` Node suites passed**. Python 3.12.14, Node v24.19.0; installed pinned requirements match requirements.txt (FastAPI 0.115.12, uvicorn 0.34.2, httpx 0.28.1, pytest 8.3.5, websockets 15.0.1, numpy 2.2.6).

All 191 project Python files parsed; `app.main` imported; report checksum/code hashes and all 16 subcase statuses validated. New-file whitespace and credential-pattern/manual reviews passed. Protected runtime/strategy/risk/scheduler/SQL/frontend/dependency diff is empty. There is no changed JavaScript requiring a separate syntax check. Optional ruff/mypy/bandit/coverage were NOT RUN.

The managed environment used the existing `scripts.replay_aura_csv.enable_sandbox_poll()` test-runner shim and disabled pytest cache; no production code was changed for test accommodations. The first full run found the incomplete new unit-test setup described above (1207 passed, 1 failed); the corrected final full run is completely green.

## What is still required for live autonomous verification

No Render deploy is required for this CLI-only change and none was performed. Do not run test signals against production. On the already-running owner-authorized Auto Paper instance, wait for an actual market-derived signal. Read the existing owner-only LIVE PAPER TRADING MONITOR and durable journal; capture source, UTC candle/run/position IDs and committed SIGNAL → OPEN → POSITION_UPDATE → CLOSE_TP/CLOSE_SL with matching fees, net PnL and balances. Confirm persistence after a genuine Render restart, scheduler operation while the browser is closed, and absence of duplicate entries, using read-only observation. Live Supabase transaction/durability and external scheduler delivery need their own actual evidence.

Only a real matching committed OPEN and CLOSE on Render with production provenance can establish LIVE AUTONOMOUS EXECUTION = VERIFIED. A replay, this report, mocked Supabase, a healthy scheduler response, or an existing trade counter cannot establish it.
