# Aura 5.0 — simultaneous LONG/SHORT scenarios

The Signals screen keeps both directions visible for 5m, 15m, 1h and 4h,
including below the user's display threshold. Each direction has its own frozen
0–100 directional technical score. This is never an estimated win probability.

`dual_scenarios` contains eight rows. A side is UNKNOWN (null score and levels)
when fresh native closed candles, a valid score, or current executable Bitget
Bid/Ask are unavailable. Existing 5-second quote and candle-cutoff checks apply.
The browser independently expires displayed data between polling requests.

For each direction, the selected frozen BASE family is ranked by: all gates
passed, fewest failed setup/trigger/planning checks, highest quote-priced Net R/R,
then family name for deterministic ties. The score describes the direction,
not an independently calibrated ranking of individual strategies.

WATCH_RESEARCH requires the existing setup AND technical trigger, valid entry
zone including modeled fill, unexpired plan, fee/slippage/funding-inclusive Net
R/R >= 1.5, and the existing minimum technical score 50. The browser can apply a
higher user threshold. Other known-data states are REJECTED, with explicit rule
failures; a failed R/R can be displayed if its calculation is valid. Missing or
invalid plans receive null levels, never the old illustrative ATR substitute.
The former score-only WATCH without a trigger is intentionally removed, including
from legacy event presentation. Neither formulas nor strategy thresholds change.

NO_EDGE_FOUND and UNVALIDATED remain in force; no new CONFIRMED eligibility,
execution authority, exchange writer, account connection or trade is introduced.
The approved registry remains empty. Manual copy and sound require a fresh,
technically accepted WATCH and remain optional. Rejected/unknown cards have no
copy action. Details are collapsed to keep Android cards compact. Diagnostics
are translated into Russian while server reason codes remain auditable.

## Evidence and review

- Base: `099f0a7`, branch `feature/aura-live-manual-trader5`.
- Public Bitget GET probe: `docs/evidence/dual-scenarios/bitget-public.json`.
  All four frames returned 260 actual closed native candles; quote ages were
  approximately 0.10–0.12 s. Both sides were correctly rejected in this snapshot.
  This verifies transport/input/render-contract behavior, not profitability.
- JavaScript regression: 442/442 passed before final presentation text changes;
  focused Node suite passed after those changes. Full CI runs on the PR head.
- Python AST parsing and changed JS syntax checks passed. Focused Python and
  full Python/Chromium outcomes are recorded in the PR checks/report.
- Local Chromium installation failed with a truncated archive. The existing
  exact-head browser workflow runs desktop and Pixel 7 Chromium emulation.
- Separate code/security review: no new network destination or dependency; no
  account credentials; UI uses textContent, not HTML injection; no order or
  deployment paths touched. Freshness, cost convention and source identity
  remain enforced. Optional forward history is separate from account history.

Local test runtime: Python 3.12.3, FastAPI 0.115.12, httpx 0.28.1,
NumPy 2.2.6, pytest 8.3.5. Local missing isolated PostgreSQL/browser facilities
must not be reported as CI PASS; GitHub workflows provide the pinned gate.

No merge, deployment, production configuration, PAPER/Active43 activation,
account/tariff change, or transaction was performed.
