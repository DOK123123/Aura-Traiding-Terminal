# Manual Analyst — isolated offline replay architecture (design, not deployed)

## Decision

Do not add VectorBT to the FastAPI environment. At reviewed commit
8e30b8ce102f302bec0c0226e05b59714453bebd it requires numpy>=2.4.6 (Aura pins
2.2.6), pandas>=3.0.3 and Numba>=0.66 plus scientific/notebook dependencies.
Its Apache 2.0 + Commons Clause needs a separate licensing decision for any
commercial integration. High-throughput vectorisation does not automatically
implement availability timestamps, pivot confirmation, adverse gaps, orders with
unknown state or multi-timeframe synchronization. No runtime integration was tested.

Existing `app/lab/execution.py` already has a network-free deterministic Decimal
simulator, conservative gap/SL-first exits, next-open signals, costs and metrics.
Reuse its accounting **after parity tests**, rather than writing another ledger.
Do not directly reuse `app/lab/models.py` as a Bitget data contract: its SOURCE is
Binance Spot, accepted frames 15m/1h/4h; it cannot label Bitget Futures/5m honestly.
No edits to Lab, Active43, models, SQL or schedulers are part of this stage.

## Proposed boundary for the next separate PR

`research/manual_analyst_replay/` (CLI only, no import into app/main):

- `dataset.py`: immutable, validated closed OHLCV windows, exchange/contract,
  native timeframe, raw file checksum, gap/duplicate/time/unit/volume checks,
  received_at/available_at, funding provenance and previously viewed periods.
- `config.py`: frozen rules/version, fee+slippage+spread+latency assumptions,
  tick/lot/minimum notional metadata with validity dates, risk<=0.5%, one position,
  notional cap, daily loss and drawdown limits; canonical config hash.
- `adapter.py`: replay timestamp advances monotonically. Supply only candles
  whose available_at<=decision_time. Resample only completed coherent windows.
  Call pure closed-window analysis; pivot i is unavailable until i+2 closes.
  Emit `{id, decision_time, available_at, valid_until, side, levels, config_hash}`.
  User annotations or manually chosen notebook exit prices are NOT signals.
- `execution.py`: explicitly review adapter to existing Lab Decimal engine.
  Earliest entry is the **next available** bar after signal availability+latency,
  with spread and adverse slip. OHLC open is an execution model, not guaranteed
  Bitget fill. Revalidate geometry/risk at actual modeled fill; SL-first if both
  touched, adverse gap stop, no same-pre-entry range exits or duplicate IDs.
  No private clients, store, account, activation or production API dependency.
- `report.py`: hash config/data/code/splits, full decisions/rejections/fills,
  fees/funding/slippage separate, liquidation equity and drawdown, undefined
  metrics honest. Baselines cash and BTC buy/hold. Cost stress x1.5/x2.

Do not add a public/production backtest HTTP endpoint. Resource budgets/max rows/
wall-clock limit enforced at CLI; local output directory separate from app stores.
Missing funding, bid/ask or intrabar ordering must remain explicit limitations.

## Mandatory parity gate before historical claims

Independent Decimal known-answer LONG/SHORT, TP/SL, adverse gap, same-bar ambiguity,
zero volume, missing history, stale signals, fees inclusive risk, insufficient
margin and duplicate/restart replay tests. Compare prefix results with full-run
results restricted to that prefix (including pivot availability, not pivot time).
Freeze configs/splits and record reused development/validation/OOS periods before
running. No new independent OOS may be declared without provenance. Backtest
profit alone never establishes a profitable strategy or authorizes trading.

## Present delivery

This document is architecture only. There is no new replay runner, historical
PnL, parameter search or profitability claim. The browser notebook merely
calculates a hypothetical price-to-price result, validated by independent sums;
it is neither the proposed backtester nor an executable account.
