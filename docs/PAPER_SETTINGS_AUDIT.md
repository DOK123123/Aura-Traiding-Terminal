# Paper settings visibility and safety audit

The Paper Trading Settings section is above Auto Paper and uses the authenticated
existing `GET /api/paper/state` response. No new settings mutation endpoint exists.
`effective_settings` contains the persisted values, ALL-account balance/equity,
source information, edit capability, starting-balance lock and Auto defensive caps.
Values are formatted for readability only in JavaScript; exact Decimal strings
populate the existing editable form. No money arithmetic moved into the browser.
MANUAL/AUTO statistics filters cannot replace the account-wide settings balance.
Unavailable equity is shown as unavailable, never zero or a simulated fresh mark.

## Actual defaults and precedence

| Setting | New-ledger default |
|---|---|
| Virtual starting balance | 10,000 USDT |
| Stop Loss fallback | 2% |
| Take Profit fallback | 4% |
| Commission per side | 0.10% |
| Slippage | Unsupported / not modeled |
| Maximum risk per trade | 1% |
| Maximum notional | 2,000 USDT |
| Maximum open positions | 1 |
| Auto mode / market | OFF / BTCUSDT / 15m |
| Auto fallback policy | SKIP |

These are simulation settings, not asserted exchange fees. Current balance/equity
change with actual virtual ledger activity. Percentage SL/TP are fallback/default
values, not absolute stops of existing positions or invented strategy outputs.

A new ledger initializes each setting from `PAPER_<FIELD_NAME_UPPERCASE>` if present,
otherwise defaults. Examples: `PAPER_COMMISSION_PCT`, `PAPER_STOP_LOSS_PCT`,
`PAPER_MAXIMUM_SIMULTANEOUS_POSITIONS`. Invalid environment values fail initialization.
Existing persisted configuration takes precedence, even if environment changes.
Initialization provenance is recorded for new ledgers; edited values are marked
persisted configuration. Old ledgers without provenance explicitly report original
source unknown. No credentials or arbitrary environment contents are returned.

## Editing and activation

Editing reuses existing validated `POST /api/paper/settings`, owner Basic auth and
same-origin `X-Aura-Paper` protection. Starting balance is locked after any trade;
fees/stops/settings edits never rewrite an existing trade. Unsafe manual settings
remain allowable while Auto is OFF under existing validation; they are not silently
reduced. If Auto is armed (including PAUSED/ERROR), unsafe edits are rejected
transactionally; explicitly switch OFF before changing to manual-only settings.

Auto ON/RESUME now runs a server-side preflight in the same SQLite transaction as
activation. It checks valid persisted settings, saved risk ≤1%, saved maximum
positions exactly 1 and no more than one existing open position. It checks finite,
positive LONG/SHORT percentage-derived stops on the correct side of entry using
64-digit Decimal context, and validates protection on existing positions against
their original entries. It requires SKIP or PAPER_SETTINGS, and the virtual-only
execution boundary. Failure returns a fixed actionable error, leaves settings,
Auto state/watermarks and trade history unchanged, and never clamps a setting.
Idempotent ON retries and restart resume are subject to the same gate. OFF always
remains available independently of a failed configuration audit.

SKIP is a valid conservative policy: signals without complete strategy SL/TP do
not open positions. Current Aura signal adapter does not supply SL/TP, so SKIP
normally means no Auto entries. PAPER_SETTINGS must be explicitly selected to
permit the existing percentage fallback. Preflight does not create stops in the
strategy, change formulas, or guarantee a trade will pass fee-inclusive entry risk.
Freshness/source checks, closed-candle decisions, per-entry stop checks, sizing,
fees, SL/TP execution and duplicate watermarks are unchanged. Existing defensive
Auto caps remain, visibly documented; activation no longer silently relies on them.

The UI blocks ON with missing/failed audit, stale/unloaded state or unsaved settings
drafts. Selecting ON or changing policy does not itself activate anything; the
owner must click Apply. Server validation is authoritative even if UI is bypassed.

## ECC review evidence and limitations

Separate architecture, Python/API, security, trading-math, frontend and regression
passes verified existing settings reuse, transaction atomicity, no strategy/private
account/Lab dependencies, finite directional protection, ALL-account scope and
honest provenance. New tests independently check LONG/SHORT stop sides, environment
initialization/persisted precedence, legacy provenance, invalid prices/settings,
rollback on rejection, edit-while-armed safety, untouched history, malformed optional
provenance, independent Fraction stop-price references under low Decimal context,
owner API and UI
states. Existing Auto fixture now explicitly saves safe limits before activation;
its previous 10%/3-position manual configuration is covered by rejection tests.

No strategy, signal, sizing, fill or SL/TP formula was redesigned. The demonstrated
visibility/safety defect was hidden Auto caps allowing ON with conflicting saved
risk/position limits; activation now rejects that conflict instead of silently
adapting it. There is no new execution authority or exchange network client.

SQLite keeps history on the same disk; Render Free disk may disappear on instance
replacement/redeploy. Provenance cannot reconstruct settings origins before this
release. Risk settings are caps, not protection against unlimited adverse gaps.
Slippage remains unmodeled and preflight is a configuration audit, not assurance of
fresh market data or fee-profitable targets. Browser/Render/Android live checks and
exact requirements-pinned dependency tests were not run; mobile validation here is
offline DOM/CSS and JavaScript coverage. No real credential requests were made.

Manual Render/Android check: owner login; panel appears before Auto; compare exact
form values with effective cards; filter AUTO and verify settings balance remains
ALL; edit/save safe settings; failed risk>1/maxpositions>1 activation reports reason
and remains OFF; choose explicit fallback; enable only if intended; inspect no entry
on baseline; OFF remains usable; existing history survives settings edits; labels,
controls, unavailable equity and source text remain readable on narrow screens.
