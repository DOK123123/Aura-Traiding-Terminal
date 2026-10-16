# STAGING VERIFICATION REPORT

**RELEASE_READY = FALSE**

**RENDER_STAGING_VERIFIED = FALSE**

The supported result is local production-like acceptance, not a Render deployment or live autonomous trading verification. No merge, production deploy, paid resource, paid API, real exchange order, production key or production Supabase access was performed. No private research bundle was published.

## Scope and environment

Base: Draft PR #10, runtime source `bf29a04c715fcf3ef93a87a4e6a676376d052440`. This PR adds verification tooling, tests and evidence only. Application code, static UI, strategy parameters, risk, scheduler, SQL and dependencies remain byte-identical to #10. The #10 protected-production hash audit remains applicable to main.

A disposable Git-archived checkout runs the **actual `start_web.py`, single uvicorn worker, FastAPI lifespan, startup/shutdown and background services** over TCP. The test-only wrapper binds loopback, selects the asyncio loop, optionally applies the existing cloud wakeup accommodation, denies non-loopback DNS/connects and limits address space. These adaptations are not installed in production code.

The subprocess environment is an explicit allowlist: dummy local owner password, isolated Paper/Lab SQLite paths, LLM disabled, no Supabase credentials, exchange keys, proxy credentials or inherited production settings. The primary profile sets `RENDER=true` to exercise deployment guards. Auto Paper correctly refuses to operate without a durable backend: its monitor returns controlled 503 with no live verification. This is expected isolation behavior, **not proof of configured production Supabase compatibility**.

A secondary profile removes the simulated Render flag and uses a new isolated Auto Paper SQLite store, defaults OFF. Its real monitor route is checked without starting trading or invoking scheduler ticks. Existing full-suite temporary virtual-cycle tests remain separate from real-market evidence.

Actual Render service creation was not attempted: no configured Render access/plan or free staging entitlement was available. Nothing was purchased or provisioned.

## HTTP and real browser checks

The local Chromium run checks real HTML/JavaScript with a disposable profile: authenticated refresh, experiment history, all seven runs of a large annual result, Auditor REJECTED status, record pagination, disabled mutation controls and AI_NOT_CONFIGURED. Anonymous/wrong-password Research API reads return 401; the static HTML shell contains no private report. There is no HTTP import endpoint. Authenticated production Research queue/run/LLM/recovery requests return 403 and cannot start heavy computation.

Chromium is installed locally; no paid browser service or package download is used. Its container-required `--no-sandbox` mode and proxy isolation are test accommodations, not a browser security certification. Browser memory/CPU are separate from reported web-process measurements.

## Storage, restart and recovery

Input is the already-public frozen Volatility Breakout annual report from PR #7, not a private user portfolio or synthetic backtest. The full 36,461,574-byte report is saved through production chunked Store, reconstructed exactly and exported without SQLite, LLM calls/prompts, environment or credentials. The fixed runner does not receive trading/LLM keys. Credential-pattern/schema tests and owner publication review requirements remain in force; no filter can certify arbitrary secret text.

A **local Git repository with no remote** commits the public snapshot; archive/checkout restores identical file hashes into the disposable runtime checkout. No source repository branch or public Git remote is changed by this exercise. A new process loads the same checksum. This tests the Git persistence mechanism; retention of the owner's remote/backup and real Render rebuild behavior still require operator acceptance.

SQLite backup/restore preserves and reconstructs the same research report in a separate store. Duplicate export is rejected without overwrite. A corrupted first decision chunk returns controlled 503 while health remains 200; restoring its bytes recovers the API. A corrupted index returns controlled 503 after restart while terminal health remains 200; restoring the index and restarting recovers Research. The isolated Paper state is unchanged by Research traffic and restart.

The temporary staging directory is removed after the exercise. Production persistence must continue to use reviewed Git artifacts or a genuinely persistent external research store with off-device backups, not runtime edits on Render's ephemeral disk. No trading Supabase table, schema or existing ledger is touched.

## Load and resource measurements

Exact measured values are in `RESEARCH_STAGING_VERIFICATION.json`, under `performance`: web-process RSS/high-water RSS, virtual address space, CPU seconds, one-core mean CPU percentage, p50/p95/max latency and per-route results. Traffic is a bounded batch of **240 requests at concurrency 12** across health, Research overview, a 100-record page and Paper state. Strategy Lab is also warmed and checked through its real API. This is a local smoke/load sample, not a sustained Render capacity guarantee.

Observed web-process measurements (local bounded batch, not Render capacity):

| Measurement | Result |
| --- | --- |
| Requests / concurrency | 240 / 12 |
| HTTP errors | 0 |
| Baseline / peak sampled RSS | 139.91 / 143.33 MiB |
| Total p50 / p95 / max | 31.18 / 236.73 / 305.08 ms |
| Health p95 / max | 32.76 / 44.22 ms |
| Paper-state p95 / max | 280.37 / 305.08 ms |
| Web CPU during 1.285-second batch | 0.98 CPU seconds, 76.25% of one core on average |
| End virtual address space | 1,513.52 MiB; virtual reservation is not RSS |

The sample is short, warmed and excludes an active production market/Supabase workload. It demonstrates responsiveness for these requests, not sustained capacity or future uptime. Virtual space is close to the diagnostic guard; do not infer memory-plan requirements directly from that number.

### Initial resource failure and control

An initial test used `RLIMIT_AS=512 MiB`, incorrectly treating virtual address space as a Render RAM limit. It produced `RuntimeError: can't start new thread` in FastAPI/AnyIO dependency workers. The same load on **unmodified main** reproduced it: 13 of 24 Paper-state requests returned 500, while RSS high-water was only **119.46 MiB** and virtual size about **506.50 MiB**. See `RESEARCH_STAGING_ADDRESS_SPACE_CONTROL.json`.

The verification setup was corrected to use a **1,536 MiB address-space guard and separately measure physical RSS**. This changes no production resource setting or thread policy. Render/cgroup RAM and RLIMIT_AS are different controls; no assumption about the current paid/free Render plan is made. Do not apply the original 512 MiB virtual-space setting as deployment advice.

A second test-tool defect selected an arbitrary decision-chunk filename before reading offset zero. The correct application could therefore return 200 from an untouched chunk. The fixture now deliberately corrupts `chunk-0-decisions-0.gz`. This was not a production corruption-handling defect. The initial secondary-profile path also used a filename rejected by the existing Auto Paper storage-scope guard; it now uses the required `auto-paper-42.sqlite3`. The production guard was preserved.

## Regression, reproducibility and review

Final regression: **1,316 Python tests passed**, zero failures/xfail, one existing Starlette/AnyIO deprecation warning; all **20 JavaScript suites passed**. Exact commands, versions and tool hashes are in `RESEARCH_STAGING_TEST_RESULTS.json`. All existing Strategy Lab, Paper Monitor, no-look-ahead, accounting, security/auth, chunking, restart, fault-handling and no-LLM checks are retained. Additional staging-tool tests cover the environment allowlist, loopback rules, local-only guard, process metrics and remote-free Git roundtrip.

Four annual hypotheses / **28 runs were recomputed again in the external CLI runner** on this branch. Financial metrics, trades, decisions, curves and causal checks match the published reference. Evidence: `RESEARCH_STAGING_REPRODUCIBILITY.json`. These are previously reused exploratory BTCUSDT data; all strategies remain REJECTED. There is no new independent profitability result or Paper promotion.

Separate review passes inspected the tooling's environment boundary, trusted-source archive extraction, bounded response paths, subprocess cleanup, local-only browser/network behavior, no-remote Git operations and error reporting. No runtime or strategy patch was needed. Failure logs remain temporary local diagnostic files and are not committed. Optional third-party scanners/penetration testing were not performed.

## Remaining blockers and readiness decision

Local success cannot satisfy checks that need actual deployment infrastructure. **RELEASE_READY remains FALSE** until the owner completes:

1. A genuinely isolated Render staging (only if free/approved) or an explicitly accepted alternative, with the eventual deployed commit, TLS/reverse proxy, actual RAM/CPU limits and restart/rebuild checks. RENDER_STAGING_VERIFIED stays FALSE here.
2. Actual persistent-disk/off-device backup acceptance on the selected local research host, and verified retention/rebuild of any published Git snapshot. The test host's physical durability is not attested.
3. Review of the privacy and checksum of any real snapshot before publishing it. No automatic publication is authorized by passing tests.
4. Configured-backend and scheduler health acceptance in a separately authorized staging setup without production credentials. This exercise deliberately leaves primary Auto Paper fail-closed and does not verify the live production market/Supabase flow.
5. Review of PR #10 plus this verification PR and explicit permission for any future merge/deploy. No production operation follows automatically from the readiness report.

Research adds no new trading authority or known runtime regression. Any later deploy still restarts the shared terminal process; the existing restart/pause protections and subsequent scheduler ticks must be checked by the owner. This exercise did not restart production. Residual risks include actual service limits, operational backup discipline and deliberately untested live integrations. The initial low-AS failure exists on main as well; it is not evidence that Research modified Aura 4.2. No claim of LIVE VERIFIED is made.

## Cost and owner instructions

No additional payment was incurred. Existing local Linux/WSL hardware, disk, Git and installed Chromium suffice for this verification; no paid API is necessary. A free Render staging entitlement and current plan limits are unknown. Do not create a chargeable preview, disk, database or API subscription automatically.

To reproduce locally, use the complete checkout and pinned dependencies, installed Chromium and an external writable scratch parent (not checkout/temporary storage for the durable-store checks):

```sh
python -m scripts.verify_research_staging --scratch-parent /home/USER/aura-staging-tests --output /home/USER/aura-staging-report-NEW.json
```

Create the scratch parent first. On this managed cloud host only, `--sandbox-poll` is needed; it remains test tooling. The command refuses Render, creates disposable local resources, never publishes its snapshot and requires a new output path. Raw logs/profiles are temporary. Replay runs remain in the separate `scripts.research_runner` CLI; this verifier never runs a backtest in the web process.

For safe next steps: review both Draft PRs; retain Auto Deploy controls; reproduce local backup/restore on the actual intended host; approve a public snapshot only after privacy review; if free isolated Render staging is available, verify it without production credentials and record its resource/restart evidence. Then request explicit merge/deploy approval. The normal research runner and snapshot commands are documented in `AURA_RESEARCH_LAB_RELEASE_READINESS.md`. Do not run a research worker on production Render or alter existing Supabase/trading data.
