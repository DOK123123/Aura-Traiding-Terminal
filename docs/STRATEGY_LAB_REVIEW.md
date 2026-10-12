# Strategy Lab v1.1 review evidence

ECC/Aura guidance was applied as separate review passes, not autonomous agents.
No changes were made to original strategy, private accounts or Paper/Auto modules.

## Architecture and security

The isolated `app/lab/` package contains validation, indicators, experiments,
Decimal simulation, immutable storage and owner-only research API. Main only wires
an injected public GET page reader and routes. No exchange execution/private-client
import exists in Lab. Static guards and integration tests verify read-only public
transport, two research POST routes only, immutable pre/post Paper state and
unchanged production modules. POST requires owner Basic auth plus a research CSRF
header. Unsupported configuration fields fail instead of enabling execution.
Bounded fetch/compute/decompression and cancellation prevent unbounded concurrent
jobs; no network operation is performed in arithmetic/strategy/storage code.

## Independent trading-math / look-ahead review

LONG/SHORT PnL, fees, adverse slippage, quantities and risk are checked against
independent Fraction arithmetic in tests. Decisions on every prefix match the
corresponding full-series decision; a current Donchian bar cannot enter its own
prior channel. Entry uses next open. Pre-entry candle extrema cannot trigger exits.
Warm-up and independent validation ledgers prevent carried development cashflows.
Gap stops, ambiguous SL/TP, priority of protection, rounded collateral and final
segment closure have explicit tests. Decimal-context tests verify stable outputs.

## Proven issues found and fixed in the new subsystem

- High: absolute target distance could treat a target below the slipped entry as
  positive net reward. Use direction-signed reward and reject nonpositive reward.
- Medium: shared frontend pattern-control selectors could couple Lab numeric
  inputs to existing analysis validation. Use separate Lab-only control class.
- Medium: retention ordered by dataset date could evict a newly inserted study
  of older history. Retain by insertion sequence instead.
- Medium: stored decompression could accept trailing bytes. Reject unused data.
- Medium: response size needed a streaming bound before JSON decode. Public GET
  page reader enforces 1 MB while streaming, with a regression test.
- Low: equity sampling could imply uniform time spacing. Plot actual timestamps.
- Reproducibility: include Python version in algorithm hash/report; replay across
  changed runtime is rejected explicitly rather than claiming bit-identical math.

Architecture, Python/FastAPI, frontend, security, trading math, causal validation,
reliability and testing passes are supported by offline regression tests. Review
is not independent third-party certification and does not authorize trading.

## Validation limitations

All source/account transport in tests is mocked. No credential-bearing request,
live historical fetch, Render run or mobile browser validation was performed.
Installed sandbox package versions differ from requirements pins. Optional ruff,
mypy, bandit, vulnerability databases and exact pinned dependency testing were not
executed. Static secret and endpoint searches are evidence, not proof against all
possible secrets/vulnerabilities. Actual test totals are recorded in delivery.
