# AURA AI RESEARCH LAB v1

Isolated manual research, not an autonomous trading system. No strategy is promoted or activated. No production portfolio, Supabase, scheduler, risk rules or exchange integration was changed. No merge or deploy was performed.

## Architecture inspected before implementation

| Branch / PR | Actual contents and use |
|---|---|
| `main` c50fd0bb2402bd261089142c96d4e9981f4594ab | Existing Strategy Lab indicators/strict importer/Decimal kernel, owner authentication and mutation protection; older offline candidates and contaminated-period research |
| Draft #3 | Aura4.3 scenarios, frozen90-day evidence and native context replay; NOT in main |
| Draft #4, depends on#3 | Conservative/Balanced/Active study, causal checks and six-month data; NOT in main |
| Draft #5, depends on#4 | Lab v2 native risk adapter, replay/metrics, independent accounting oracles, annual Binance candles and comparison UI; NOT in main |
| Draft #6 | Separate isolated production execution harness, based on main; inspected, not imported and NOT a dependency |

**This is a stacked Draft PR on `codex/strategy-lab-v2` at758ffb48a14ab1ad852b7bf431c29c0262e9cc9d. Dependencies: #3 → #4 → #5.** The incremental diff excludes those already-developed components. Main must not be assumed to contain them. After separately authorized parent integration, rebase/review this PR before any release. Nothing here merges a parent PR.

The module `app/research/` contains a manual Agent Orchestrator, frozen Strategy Registry, persistent Research Queue, Experiment History and Audit Reports. No timer, autonomous loop or new scheduler exists. Only two integration lines in app/main import/register the new router; the existing production lifespan is unchanged.

## Three capability-limited agents

- **RESEARCHER**: curated frozen hypotheses with sources, economic rationale, explicit limitations and configuration hashes. Optional real LLM API adapter can propose an advisory idea. Deterministic protocols are labelled `CURATED_FROZEN_PROTOCOL_NOT_LLM`; they are never presented as generated AI output.
- **BACKTESTER**: calls the existing `scripts.research_lab_v2.replay` and `app.lab.v2_execution` on fresh isolated RAM accounts, using the unchanged native fee-inclusive risk and protective execution functions. Cannot access a production Service/store or exchange writer. Native policy: 10,000 initial virtual units, planned risk0.5%, daily2%, drawdown10%, one position, notional2000, fees10bps/side, slippage5bps/side. Gap losses may exceed planned risk.
- **AUDITOR**: separate deterministic exact Fraction fill/fee/PnL/risk/PF/expectancy/WR checks, reuse of the independent PR5 raw-candle first-touch and complete open/close equity/MaxDD oracles, independent Sharpe checks, split-boundary causal prefix checks, sample and fixed parameter-sensitivity review. Cannot place orders or approve activation. Python `-O` is rejected because the reused oracles require assertions.

These are actual separate application roles with bounded code capabilities, not three simulated LLM conversations or claims of three paid models. Deterministic Backtester/Auditor require no LLM. Version1 LLM support is advisory for Researcher; no LLM result is executable code, parameters, SQL, a provider URL or a trading instruction.

## Hypotheses and checked scientific sources

Six DOI metadata records were checked through Crossref during this task. Sources motivate hypotheses; none establishes these thresholds or present BTC intraday profitability.

| ID | Literature / domain | Use and limitation |
|---|---|---|
| JEG1990 | Jegadeesh1990, Evidence of Predictable Behavior of Security Returns, https://doi.org/10.1111/j.1540-6261.1990.tb05110.x | Monthly US stock reversal; not BTC15m evidence |
| CONT2014 | Cont/Kukanov/Stoikov2014, The Price Impact of Order Book Events, https://doi.org/10.1093/jjfinec/nbt003 | Equity order-book microstructure; OHLCV cannot establish stop hunts/liquidity removal |
| BROCK1992 | Brock/Lakonishok/LeBaron1992, Simple Technical Trading Rules and the Stochastic Properties of Stock Returns, https://doi.org/10.1111/j.1540-6261.1992.tb04681.x | Historical Dow technical rules; no BTC net validation |
| HAM1989 | Hamilton1989, A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle, https://doi.org/10.2307/1912559 | Regime methodology, not trading edge; our threshold classifier is not a fitted Hamilton model |
| MOP2012 | Moskowitz/Ooi/Pedersen2012, Time series momentum, https://doi.org/10.1016/j.jfineco.2011.11.003 | Traditional futures; no intraday BTC inference |
| LIU2021 | Liu/Tsyvinski2021, Risks and Returns of Cryptocurrency, https://doi.org/10.1093/rfs/hhaa113 | Crypto return predictability; not proof for this cost/execution setup |

1. **Mean Reversion** reuses `scripts.research_candidates.Candidate C` entry conditions (RSI14 re-entry30/70, ADX<=20, EMA spread/ATR<=0.5). This distinct experiment intentionally ignores C's RSI/ADX discretionary exit flags and uses only protective SL2ATR/TP4ATR.
2. **Liquidity Sweep** is explicitly an **OHLCV failed-breakout proxy**. Previous20-bar range excludes the current bar; pierce by0.1ATR then reclaim, directed body, relative volume>=1.2 and ADX<25. LONG/SHORT mirrored; SL2ATR/TP4ATR.
3. **Volatility Breakout** delegates existing v2 DONCHIAN unchanged, including prior-range breakout+0.1ATR, EMA20/50, ADX>=20, relative volume>=1.25, directed body, shock-candle rejection and cost-adjusted RR>=1.2. No duplicate breakout engine was created.
4. **Market Regime Switching** uses only the latest fully closed1h ADX: <=20 selects reversion, >=25 selects existing TREND_ATR entry on15m, transition waits. No full-series HMM fit/smoothing. 4h candles are available and prepared as context, but do not filter entries in v1.

All inputs are closed; entries are queued and executed at the next15m open, with protective SL-first ambiguity and conservative/adverse gaps inherited from Lab v2. No future candle chooses a signal, pivot or regime. No training optimizer exists. No parameters were changed after observing these experiments.

## Available real data and contamination

Reuses existing PR5 `docs/data/LAB_V2_BTCUSDT_15m.csv.gz` and acquisition provenance, rather than fetching or duplicating candles. Source: **Binance Spot public REST `https://data-api.binance.vision/api/v3/klines`, BTCUSDT15m**. No Bybit Futures or exchange-source mixing. SHA256:

`da31330b7d5df5bf9560171372e6f4157d3215ef236ef528a529089f6a823810`

39,200 real rows: 4,160 warmup and35,040 evaluation candles, evaluation2025-10-16T00:00Z..2026-10-16T00:00Z exclusive (365 days). Strict existing importer rejects missing/duplicate/unclosed/malformed OHLCV; complete UTC1h/4h aggregation only. No synthetic performance inputs. Synthetic fixtures appear only in invariant tests.

Main research also examined earlier periods. A conservative observed-period ledger marks2020-01-01..2026-10-16 exclusive as previously examined, including prior declared holdout exposure. The entire supplied year was published in PR5. A new60/20/20 split **does not reset that exposure**. The final split is `REUSED_EXPLORATORY_TEST`, not a fresh independent test. No rename, repeated job, new hash or parameter choice can enable promotion in v1. A fresh independent dataset is not available in this version.

## Frozen experiments and results

`docs/AI_RESEARCH_V1/frozen_plan.json` was written exclusively before any financial metrics. It records the UTC freeze, source, all hypotheses, policy, code hashes, full parameters and config hashes. Each manual queue entry also stores its frozen config before dispatch. Random queue IDs identify attempts; config hashes identify reproducible experiments. No test-period optimization or winner selection occurs.

Seven fresh-ledger runs per hypothesis: train scales0.9/1/1.1, validation scales0.9/1/1.1, test scale1 only. The scale changes stop AND target distances ±10% around the frozen strategy; it is a descriptive sensitivity check, never a selection search. All28 results are reported, including losses. Across four hypotheses/multiple trials, positive values cannot be treated as independent discoveries.

No terminal forced close: open positions retain liquidation equity and pending plans remain explicit. Net/return include terminal open-position marks; Win Rate, PF and Expectancy describe closed trades. Split results cannot be added as one continuous compounded account.

| Hypothesis | Split | Closed trades | Net USDT after costs | Return % | PF | Win % | Expectancy | Max DD % | Sharpe | Fees |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MEAN_REVERSION | train | 6 | 4.27362472 | 0.04273625 | 1.07060951 | 50.00000000 | 0.71227079 | 0.36745572 | — | 24.08309799 |
| MEAN_REVERSION | validation | 2 | 11.25894373 | 0.11258944 | 1.70833813 | 50.00000000 | 5.62947186 | 0.15851828 | — | 7.95697054 |
| MEAN_REVERSION | test | 3 | -47.43747595 | -0.47437476 | 0.00000000 | 0.00000000 | -15.81249198 | 0.47437476 | — | 11.98022886 |
| LIQUIDITY_SWEEP | train | 123 | -1001.39698317 | -10.01396983 | 0.39932937 | 28.45528455 | -8.14143889 | 10.01396983 | -6.0035387273533125 | 491.56724785 |
| LIQUIDITY_SWEEP | validation | 64 | -427.21583445 | -4.27215834 | 0.43879609 | 32.81250000 | -6.67524741 | 4.90522295 | -7.164622958536844 | 255.94236225 |
| LIQUIDITY_SWEEP | test | 63 | -323.89987068 | -3.23899871 | 0.48431688 | 36.50793651 | -5.14126779 | 3.35162318 | -4.9774606260739365 | 251.94686569 |
| VOLATILITY_BREAKOUT | train | 121 | -895.95591963 | -8.95955920 | 0.61823203 | 31.40495868 | -7.40459438 | 9.30418626 | -3.491607547009808 | 480.87595474 |
| VOLATILITY_BREAKOUT | validation | 24 | -296.85425175 | -2.96854252 | 0.41045014 | 25.00000000 | -12.36892716 | 3.48797681 | -4.704930848075863 | 96.15856283 |
| VOLATILITY_BREAKOUT | test | 15 | -32.23868951 | -0.32238690 | 0.85512947 | 40.00000000 | -2.14924597 | 1.47401242 | — | 60.08515636 |
| REGIME_SWITCHING | train | 77 | -413.49000476 | -4.13490005 | 0.73431199 | 36.36363636 | -5.37000006 | 6.85863358 | -1.5085840704113587 | 305.65199128 |
| REGIME_SWITCHING | validation | 16 | -206.18059862 | -2.06180599 | 0.40910431 | 18.75000000 | -12.88628741 | 2.71415621 | — | 63.99085891 |
| REGIME_SWITCHING | test | 10 | -213.38507777 | -2.13385078 | 0.15981255 | 10.00000000 | -21.33850778 | 2.79493647 | — | 39.89775875 |

**All four hypotheses: REJECTED. No CANDIDATE_FOR_PAPER; no confirmed independent advantage.** Mean Reversion also has far too few closed trades for a claim. Negative train/validation sensitivities or sparse samples are reported in each auditor conclusion. The sweep train ledger hits the unchanged drawdown protection; a small discrete mark/gap overshoot of10% is possible, not a protection bypass.

Complete seven-run metrics, trades, decisions/rejections, sampled equity/daily equity, open/pending states, independent audits and reproducible config are in each `docs/AI_RESEARCH_V1/<HYPOTHESIS>.json.gz`; bounded `summary.json` is visible in the owner UI without recomputation. Checksums and code hashes detect corruption/stale code, not independent authentication of financial edge.

## UI and manual workflow

On this branch, run the existing app locally (`python start_web.py`) and open **`/static/research.html`**, also linked as **AURA AI RESEARCH LAB** at the bottom of the terminal. Owner login uses the existing `aura` username and server-side `AURA_TESTNET_VIEW_PASSWORD` (minimum12 characters). No password or API key is entered into the Research Lab page.

1. Click **Обновить**: load agent states, registry, source/data identity, queue/history, published metrics and LLM log. Opening the page makes no request and starts nothing.
2. Select one of four fixed hypotheses and click **Зафиксировать в очереди**. This stores the config and unique job ID, without computing.
3. Click **Запустить вручную** for that queued job. Backtest and audit execute once in a bounded worker, then the immutable report is saved. No Paper orders or activation are possible.
4. Inspect split/sensitivity metrics and audit reasons, or download owner-only full JSON with all trades, decisions, curves and reproducible config. Repeated run is rejected; enqueue of identical config returns the same job. Reproduce independently with the CLI if desired.
5. After a process crash, work is not resumed automatically. The owner can mark RUNNING tasks older than10minutes as interrupted, then explicitly retry an ERROR task's unchanged config and separately run it. Previous failure/retry events remain in history.

The API is `/api/research`: owner-only GET overview/experiment/export; CSRF-protected POST queue/run/retry/recover-interrupted/ideas. It reuses Lab owner and mutation dependencies (`X-Aura-Lab: research-only`, same-origin checks). Responses are no-store. Unauthenticated reads/mutations never construct the storage factory. No raw exceptions, signed URLs or model headers are exposed. Frontend uses textContent, not innerHTML; only curated DOI links are rendered.

## Persistence and LLM configuration

Dedicated local SQLite: `<repository>/.data/ai-research/ai-research-v1.sqlite3`. No caller-selectable path and no production Supabase access. Application ID, existing-file checks, symlink/hardlink rejection and configured/default Paper/Lab/pattern/Auto42 path conflicts fail closed before initialization. Queue/history is bounded32experiments; reports are capped32MiB raw/8MiB compressed, database128MiB, LLM journal1000calls. One claimed experiment runs at a time across controller instances. Saved artifacts have integrity hashes. Storage is not a multi-host distributed queue.

Without configuration, `AI_NOT_CONFIGURED` is shown; deterministic agents still work. No paid call was made for this task. The optional real HTTP adapter supports allowlisted **openai** and **mistral** endpoints only, TLS and no redirects; compatible chat-completion models must support max_tokens and JSON response format. Arbitrary base URLs are deliberately unsupported.

Server environment only, disabled by default:

| Variable | Meaning |
|---|---|
| AURA_RESEARCH_LLM_ENABLED | Exactly `true` to enable manual advisory calls |
| AURA_RESEARCH_LLM_PROVIDER | `openai` or `mistral` |
| AURA_RESEARCH_LLM_MODEL | Compatible model ID |
| AURA_RESEARCH_LLM_API_KEY | Provider API key, server-only; never in browser/config/report/log |
| AURA_RESEARCH_LLM_INPUT_USD_PER_M / OUTPUT_USD_PER_M | Positive conservative prices per1Mtokens; must cover actual provider/model prices |
| AURA_RESEARCH_LLM_DAILY_USD / TOTAL_USD | Positive daily and lifetime ledger budgets; no spending without valid caps |
| AURA_RESEARCH_LLM_MAX_INPUT_TOKENS | Default8192, range2048..16384 |
| AURA_RESEARCH_LLM_MAX_OUTPUT_TOKENS | Default512, range64..2048 |
| AURA_RESEARCH_LLM_PERSISTENT_STORAGE_CONFIRMED | On Render, explicit `true` required in addition to an actually persistent research ledger |

**Spending scope is the preserved local ledger, not an external billing guarantee. Render ephemeral disk loss resets local history/counters. Keep LLM disabled unless this path survives restart and configured prices cover actual billing.** The confirmation flag is an owner configuration assertion, not a persistence test. Multi-instance hosts need a shared durable budget service in a later version; never enable independent per-host budgets as one global cap.

Before dispatch, SQLite atomically reserves worst-case configured input/output cost against daily and total budgets. Reservations are never refunded, including timeout/unknown outcome; repeated calls and restarts of the same ledger cannot reuse that allowance. Input UTF8 bytes plus a conservative framing reserve are checked, model output tokens capped, response body capped64KiB and usage validated. Journal stores only provider/model/time/reservation/status/usage; no key, prompt or raw upstream response/error. LLM errors and credential echoes fail closed. Mocked adapter tests do not establish live provider compatibility/connectivity.

The LLM produces a bounded advisory JSON idea citing only supplied source IDs. Hallucinated or unsupported content remains unverified and cannot become an executable strategy, change the registry, read held-out outcomes, or start an experiment. No automatic tools or model-driven code execution exist.

## Reproduction, validation and review

```bash
python -m scripts.run_ai_research --output-dir /tmp/aura-ai-new-study
python -m pytest -q
node tests/test_ai_research_frontend.cjs
```

The CLI uses only the bundled real dataset and unchanged kernel. It refuses to overwrite its pre-metrics frozen plan or previous reports. New runs on new data are not enabled through an arbitrary file/URL upload endpoint in v1; fresh forward data and a preregistered evaluation protocol are a next step. No LLM is required for this command.

**Final full regression: 1254 Python tests passed in90.98s**, including24 new research tests; one existing Starlette/AnyIO deprecated BlockingPortal alias warning. **All20 Node suites passed**, including12 behavioral checks of the new page. Python3.12.14 / Node24.19.0; pinned requirements match requirements.txt. All223 Python files parsed; app.main imported; changed research.js passed node --check; staged whitespace and secret-pattern/manual reviews passed. Tests used the existing test-runner-only sandbox-poll shim; no runtime event-loop change. Optional ruff/mypy/bandit/coverage and a real browser screenshot were NOT RUN; fake-DOM behavioral tests cover the actual frontend code.

Covered invariants include agent authority/import isolation, closed/future-prefix data invariance for all four hypotheses, exact metric/ledger mutation rejection, real owner HTTP success→persist→reopen, duplicate dispatch denial, manual retry and attempt fencing, configured-path/symlink/hardlink rejection, concurrent claims and budget reservations across controllers, anonymous no-storage construction, owner/CSRF/strict schema/no-store, no-LLM behavior, malformed responses/timeouts/credential echoes, conservative spending through restart and invalid-price/token-limit failures. Live LLM provider requests are mocked, not actual paid calls.

Code/security review found and corrected three research-infrastructure issues before publication: configured fresh-ledger path aliasing; inability to manually retry an interrupted frozen experiment; and a stale worker potentially completing a newly retried attempt of the same job. A per-attempt UUID now fences every result/error commit with SQL CAS. Regression tests cover all three; none involved production trading code. The reviewer reran13 focused safety/auth/persistence/LLM checks and verified all four artifacts' checksums/current calculation hashes and28 passing audits. No unresolved critical/high issue was identified in the reviewed change.

## Next stage and limits

Obtain fresh, never-inspected forward historical candles after a preregistered cutoff, independently verify acquisition provenance and coverage, and freeze selection/sample/robustness criteria before viewing results. Add a versioned data-ingestion and observed/test-consumption ledger before supporting new unseen datasets or allowing candidates; v1 conservatively prohibits every promotion. Review multiple-testing/overfitting and realistic latency/funding/borrow modeling. A new split of the same annual history is not that next stage.

If LLM is desired, configure a compatible provider/model and conservative pricing/budgets on a persistent isolated ledger; perform a separately authorized manual connectivity check. No live LLM call or Render verification happened here. Extend LLM critique to other roles only as advisory, preserving deterministic audit authority.

Review/rebase the #3/#4/#5 dependency chain and this Draft PR before any separately authorized merge or deploy. The UI becomes available on a running instance only after that instance actually runs this branch's code. Production Aura4.2, existing balances/positions/Supabase, provider diagnostics and scheduler remain unchanged. This work neither enables Paper candidates nor verifies autonomous live OPEN→CLOSE.
