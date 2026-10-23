> Final integration adds an optional owner-reviewed Git snapshot transfer. See [AURA_RESEARCH_LAB_RELEASE_READINESS.md](AURA_RESEARCH_LAB_RELEASE_READINESS.md). Earlier operational limitations below describe the PR #9 baseline.

# Research Lab release-blocker fixes

Status: **ISOLATED_RUNNER_VERIFIED / PRODUCTION_DEPLOY_NOT_VERIFIED**.
This is not a claim of production RELEASE READY, profitable strategies, or verified live trading.
No merge, deploy, paid API call, trading write, or infrastructure purchase was performed.

## Fixed audit findings

- F1: the 36,461,574-byte Volatility Breakout report no longer exceeds the old 32 MiB object limit. Results use a compact manifest and separate compressed JSONL chunks for decisions, trades, equity and daily equity. All chunks, state and manifest commit in one SQLite transaction. No monolithic HTTP report is generated.
- F2: the terminal's Research API is always a read-only viewer. HTTP cannot execute or spawn backtests. Even the separate local Workbench only queues work; a manual external CLI starts execution. Replay imports are lazy.
- F3: malformed reports return controlled integrity errors (503), not unhandled HTTP 500. Oversized stored fields are rejected before loading their contents. Chunk checksums are verified before records are returned.
- F4: runner packaging now explicitly requires the complete checkout, protocols and historical artifacts. The terminal itself no longer eagerly imports the replay engine.
- Persistence: explicit external durable storage replaces implicit ephemeral checkout storage. No trading Supabase tables or schema are used.

The manifest cap is 512 KiB; each raw chunk is at most 128 KiB / 256 records; each record at most 64 KiB; arrays at most 128 MiB / 2,048 chunks per experiment. HTTP returns at most 100 records from one bounded chunk. The SQLite database is capped at 256 MiB. Capacity exhaustion fails closed; archive and back up completed research before additional runs. These are operational limits, not unlimited retention.

## Supported launch: separate Linux/WSL computer

The cheapest option is an existing personal computer and persistent local disk: no additional service payment or LLM API is required. Keep it separate from the production host. Hardware, electricity and off-device backup remain the operator's responsibility. Optional always-on hosting/persistent disks can cost money; no plan or current Render price was verified or purchased.

Use the project's pinned dependencies and complete checkout. Replace the example paths and configure the owner password privately (at least 12 characters). Do not commit secrets.

```sh
python -m scripts.research_runner init --state-dir /home/USER/.local/share/aura-research
export AURA_RESEARCH_STATE_DIR=/home/USER/.local/share/aura-research
export AURA_RESEARCH_STORAGE_MODE=durable
export AURA_RESEARCH_LLM_ENABLED=false
# Configure AURA_TESTNET_VIEW_PASSWORD securely in this local environment.
python -m app.research.web
```

Open http://127.0.0.1:8001/static/research.html and authenticate as owner. No trading routes or terminal scheduler are started by this application. It binds localhost by default; do not expose it publicly. Creating a job does not execute it.

```sh
python -m scripts.research_runner enqueue --state-dir /home/USER/.local/share/aura-research --hypothesis VOLATILITY_BREAKOUT
python -m scripts.research_runner run --state-dir /home/USER/.local/share/aura-research --job-id JOB_ID --isolated-host
python -m scripts.research_runner inspect --state-dir /home/USER/.local/share/aura-research --job-id JOB_ID
python -m scripts.research_runner verify --state-dir /home/USER/.local/share/aura-research --job-id JOB_ID --isolated-host
python -m scripts.research_runner backup --state-dir /home/USER/.local/share/aura-research --dest /home/USER/backups/aura-NEW
python -m scripts.research_runner restore --backup-dir /home/USER/backups/aura-NEW --state-dir /home/USER/.local/share/aura-restored-NEW
```

Other hypotheses: MEAN_REVERSION, LIQUIDITY_SWEEP, REGIME_SWITCHING. Restore/backup destinations must not already exist. Backup preserves identity, reports and budget history and verifies chunks. Keep an off-device backup; a folder declaration does not attest physical disk durability. Do not use NFS or a live cloud-synced SQLite database. Do not concurrently operate multiple restored copies as a shared budget counter.

Temporary directories, checkout paths, unsafe links and missing initialization markers are rejected. Directories use mode 0700. SQLite v1 research databases are deliberately **not automatically migrated or reset**; schema mismatch is controlled and preserves the old file. Preserve a backup and use the old revision for reviewed export if prototype research must be migrated. Frozen Git reports remain available. This is a remaining migration limitation, not a trading-data migration requirement.

## Isolation and recovery

The CLI refuses writable execution on Render. `--isolated-host` is an operator declaration, not automatic proof that two machines differ. Use a separate host as instructed. The worker is a fresh child interpreter with an environment allowlist that excludes trading, Supabase, owner and LLM credentials. Defaults: 768 MiB address space, 120 CPU seconds, 180 wall seconds, 256 MiB file size, 64 file descriptors, no core dumps; minimum 512 MiB free disk headroom. Address space is not the same as resident memory.

A process lock plus atomic queue claim/attempt fencing prevents competing execution. The child inherits the lock; orphan alarm and CPU limits bound execution after parent death. Failed runs remain ERROR, and stale RUNNING jobs require manual recovery after ten minutes, then explicit retry/run:

```sh
python -m scripts.research_runner recover --state-dir /home/USER/.local/share/aura-research
python -m scripts.research_runner retry --state-dir /home/USER/.local/share/aura-research --job-id JOB_ID
```

There is no automatic scheduler, daemon or HTTP dispatch. Socket guards prohibit normal worker TCP connections. These protections are for trusted fixed research code, **not a sandbox for malicious Python**. LLM advice cannot install executable strategies. Without configured LLM API the status is AI_NOT_CONFIGURED; deterministic research and audit remain available. No new paid provider is needed.

## API and Render compatibility

Existing owner authorization, CSRF and no-store behavior remain. The compatibility run route returns `executed:false` / EXTERNAL_RUNNER_REQUIRED; clients must not treat a queued job as executed. Export now returns a CHUNKED_MANIFEST_V2, not a huge report. Records and events have explicit paginated routes. Only CLI/tests materialize full reports.

The embedded terminal viewer needs no new environment variables and can show published Git artifacts with no writable research database. Setting a role environment variable cannot enable writes in the production service factory. The retired `scripts.run_ai_research` command gives a controlled migration message.

New external-runner results are not automatically synchronized to Render. A Render viewer of those results would require a verified persistent read-only snapshot/mount and an operator-defined transfer/backup procedure. These have **not** been provisioned or tested. Render's temporary filesystem is not a supported sole research store. Do not point research storage at trading storage, add trading Supabase tables, or share credentials. No additional Render payment is necessary for the published-results viewer; external-result hosting is a separate deployment decision.

## Verification

- Full Python suite: **1,284 passed**, one existing Starlette/AnyIO deprecation warning; no xfail. All **20 JavaScript suites passed**, including 14 Research UI behavioral checks.
- Audit regressions now require both the original 36 MB report save/reconstruction and malformed-report controlled error to pass.
- Tests cover atomic rollback, corrupted/oversized manifests and chunks, bounded pagination, schema preservation, backup/restore/restart and budget history, owner access, read-only production factory, isolated Workbench routes, duplicate claims, wall/CPU/address-space limits, Render denial and sanitized child environment.
- Four real annual BTCUSDT experiments / **28 runs** were executed or independently recomputed in the external runner. All metrics, trade records, decisions and curves match the PR #7 canonical records. Manifests are about 81–83 KB. The financial parameters were not changed; lazy import placement changes the calculation-source hash, so old hashes are not rewritten or falsely declared equal.
- Source: Binance Spot public REST data-api.binance.vision/api/v3/klines; complete UTC 1h/4h aggregation from 15m; data SHA256 and details in AI_RESEARCH_RELEASE_VERIFICATION.json. 39,200 candles, including 4,160 warmup and 35,040 annual evaluation candles. This is previously reused exploratory data, **not a new independent validation period**. All four hypotheses remain REJECTED; no Paper promotion.
- During actual external runs the owner viewer/health endpoints remained responsive: maximum measured probe 0.128 seconds. First fresh viewer baseline/peak: 54.44/57.43 MiB; worker peaks 230–327 MiB. Later acceptance-process baselines include retained reference-oracle allocations between cases and must not be described as clean production viewer memory measurements. These measurements are local, not Render load guarantees.

Acceptance evidence: AI_RESEARCH_RELEASE_VERIFICATION.json. Reproduce it with `python -m scripts.verify_research_release --help`; it uses existing frozen datasets and local state only. The original audit tests are included and both former xfails are mandatory passes.

## Integration order and operational gate

Dependency chain: **#3 → #4 → #5 → #7 → this fix PR**. This PR bases directly on #7. #8 is historical audit evidence, not a runtime dependency. #6 is an independent paper execution harness; review it separately. No PR was merged here.

Before any future authorized merge/deploy:

1. Inspect current branch dependencies and conflicts again, and arrange Render Auto Deploy so merging cannot silently deploy. Re-run Python/JavaScript suites against the eventual combined head.
2. Verify trading modules, scheduler, exchange source, risk configuration, balances and positions remain untouched. No research-to-execution promotion exists.
3. On the separate Linux/WSL host, run init, real experiment, restart, verify, backup and restore; confirm actual persistent disk and off-device backup permissions/capacity. Review memory/CPU limits on that host.
4. On a staging terminal, verify owner-only read access, disabled mutation, controlled corrupt-report errors and terminal health under concurrent requests. Do not launch research workers on Render.
5. Decide explicitly whether Render needs unpublished external research results. If yes, first design/test a durable read-only snapshot transfer; this patch does not claim to supply that infrastructure.

Rollback must preserve the v2 state directory and backups. Do not open v2 databases with v1 storage or re-enable the old in-web execution route. Disable the Research integration or revert the complete Research feature if needed; do not roll back only this safety patch and leave unsafe PR #7 execution enabled. Trading ledgers must not be reset.
