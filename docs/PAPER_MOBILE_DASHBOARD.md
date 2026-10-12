# Русская мобильная панель Paper Trading

UI-only redesign. `app/` (including Paper, strategy, market data, private accounts
and Strategy Lab), APIs, authentication, risk formulas, persistence and stored
history are unchanged. No runtime dependencies, exchange endpoints or strategy
activation pathway were added. Only existing owner-protected Paper calls are used.

## Панель и источники данных

At the top: server status OFF/ON/PAUSED/ERROR, saved BTCUSDT timeframe, last
processed closed candle, latest signal, translated action/rejection reason, current
AUTO position (direction/entry/BTC quantity/SL/TP/unrealized PnL), compact last-five
AUTO trades and clearly separate ALL-account balance/equity vs AUTO-only realized
PnL/closed-trade count. Values come from backend Decimal strings; Number conversion
is for display/drawing only. Missing/undefined values are not invented as zero.

The full existing journal is still accessible with ALL/MANUAL/AUTO filtering.
When it is not AUTO, an additional authenticated `GET /api/paper/state?scope=AUTO`
provides the dashboard history/positions/metrics independently. Account values use
that response's `effective_settings` ALL account fields. Never infer AUTO results
from the selected MANUAL ledger or from the last 100 mixed ALL trades. Reads are
sequential bounded requests (35 seconds each), no overlapping polling loops.
Selecting AUTO reuses that response without a duplicate read. Across the two GETs
snapshots are not guaranteed to be atomic; each section is explicitly scoped and
uses its own authoritative response. A failed AUTO-only read leaves a valid manual
journal accessible but disables all activation and shows unavailable Auto data.

## Свежесть и честные состояния

«Нет свежих данных» replaces active dashboard claims when owner state or AUTO
snapshot is missing, expired after 30 seconds, malformed, or market freshness/
source/timeframe cannot be verified. ON also requires a recent processed closed
candle within the existing two-interval freshness allowance. Open AUTO positions
require server FRESH marks and finite numeric fields; stale PnL/equity remain
unavailable. A partial position count is not shown as a false empty position.
Snapshots cannot become fresh merely because market events continue. Last-known
mode/scope/policy may be labelled explicitly as last confirmed, not current activity.
PAUSED and ERROR do not imply trading; last processed time is historical, not proof
that a trade occurred. OPENED requires the matching decision's `trade_opened` record.

The dashboard verifies the currently selected BTCUSDT chart as a freshness witness;
selecting XAUUSD or another active Auto timeframe can temporarily make it unavailable.
Select the saved BTCUSDT timeframe/source to verify or resume. This is conservative
presentation, not a claim that the backend stops because another chart is selected.

## Управление и черновики

Start/Resume uses the **saved** fallback policy, never changes SKIP into
PAPER_SETTINGS, and requires native explicit confirmation naming virtual mode,
market and policy. Both before and after the dialog it checks freshness; the server
still enforces the existing preflight. Data is reread after acknowledgement; an
unacknowledged request cannot display successful ON/OFF or an invented trade.
Repeated taps while pending are disabled. No POST happens on load/reload/restart.
PAUSED after restart requires explicit Resume; stale/missing data blocks activation.

Stop sends the existing `{enabled:false}` operation, independent of freshness,
preflight or policy drafts. Backend OFF behavior and protective exits are untouched;
OFF does not liquidate existing positions, and protection still needs fresh data.
A sleeping/unreachable server cannot acknowledge Stop; the UI says so honestly.
An unresolved manual idempotent action retains its existing retry workflow and
blocks conflicting writes. Closing the page aborts requests; restoration reloads
state without automatic activation.

The Russian advanced section preserves the original explicit mode/policy control.
Choosing PAPER_SETTINGS is an unsaved draft until confirmed ON/RESUME through that
control; existing OFF semantics do not save a policy. Form edits survive polling;
quick Start is blocked by drafts. «Отменить черновик» restores the last retrieved
server values without any mutation. Validated settings save and starting-balance
lock remain exactly as implemented by the backend. Decimal form inputs require
a dot, as before; display uses Russian grouping/decimal separators.

## Доступность и мобильный экран

Critical virtual-only and SL/TP availability warnings stay outside collapsible
content. Native Russian-labelled details retain full journal, manual order form,
settings/provenance, decision audit and safety explanations. Buttons are at least
44px high (dashboard actions 48px), inputs 16px, focus outlines visible, tables
scroll only within labelled keyboard-focusable regions. Grids use minmax(0,1fr),
wrap long values and switch for 320–430px. No new framework/build is required.

## Проверки и review

Separate ECC architecture/security/trading-math/reliability passes checked scope,
owner/CSRF protection, saved-policy use, finite data, confirmation races, atomic
server authority and no money math/private clients in UI. Proved new-UI defects
fixed before delivery: market-event freshness extension, data aging during modal
confirmation, optimistic ON/OFF acknowledgement, drafts overwritten by polling,
false no-position on incomplete data and dashboard-read failures hiding manual UI.

Python regression tests exercise unchanged server contracts across all modes,
LONG/SHORT fee-inclusive unrealized PnL against independent Decimal references,
ALL/AUTO attribution, saved policies, restart PAUSED, null stale marks, auth,
preflight, safe OFF and absence of new routes/private dependencies. Offline Node
DOM tests cover controls, all modes, attribution, stale/sleep/missing states,
positions, confirmation rejection/time aging, pending requests, drafts, reload,
late responses, read failures and exchange-write isolation. Older English-title
assertions and mock GET scope semantics were updated to match this requested UI.

Actual browser pixel layout, native Android dialog/download behavior, live Render
and exact requirements-pinned runtime testing were NOT RUN. CSS/DOM checks and mocks
are not browser/mobile validation. Backend storage retains its existing Render Free
ephemeral-disk limitation; backup before redeploy if the existing instance has data.

## Ручная проверка на Render / Android

1. Before redeploy, download the existing journal backup if local data matters.
2. At 320/360/390/430px portrait and landscape, verify headings, long values,
   buttons and local table scrolling; keyboard-focus details/controls/regions.
3. Login, verify initial OFF/PAUSED/error comes from server; no activation on load.
4. Compare ALL account values with backend; switch MANUAL/AUTO journals and verify
   Auto PnL/trades/position/history remain AUTO-only.
5. Check LONG and SHORT cards, no-position case, decimal display and UTC dates.
6. Start with saved SKIP: confirmation must say SKIP, no implicit fallback. Cancel
   must send nothing. Explicitly opt into PAPER_SETTINGS only if intended.
7. Check failed preflight, draft warning, polling preservation and discard.
8. Stop and verify OFF acknowledgement; open positions retain protective rules.
9. Disconnect network or let Render sleep: «Нет свежих данных», no stale ON/trade
   claim; reconnect/refresh before Start. Restart remains PAUSED until confirmation.
10. Manual virtual entry/close, full journal, settings save, decision audit and
    backup export remain available; Bybit/Binance and Strategy Lab remain unchanged.
