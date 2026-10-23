# AURA RESEARCH LAB RELEASE READINESS

**RELEASE_READY = FALSE** — integrated code is tested locally; production deployment acceptance and operator approval remain outstanding. No merge, Render deploy, production API call, paid API activation, real order or production database change was performed.

## Integrated dependency chain

The integration branch starts at current main `c50fd0bb2402bd261089142c96d4e9981f4594ab` and cherry-picks, in order, all seven commits of **PR #3 → #4 → #5 → #7 → #9**. There were no conflicts, and the tree immediately after integration was identical to PR #9. Original Draft PR branches are unchanged. PR #6 is independent and excluded. PR #8 is an audit, not a merged dependency; the regression tests already delivered by #9 remain included.

| PR | Scope | Source head |
| --- | --- | --- |
| #3 | Lab-only Aura 4.3, frozen 90-day comparison | f0ae5b04dca0cea5c0c4c2f39dafbc62a3df2446 |
| #4 | Conservative/Balanced/Active research, six-month evidence | 7f5516a15944414d0b70491f68234e1f84a95a46 |
| #5 | Lab v2, annual strategies, independent accounting audits | 758ffb48a14ab1ad852b7bf431c29c0262e9cc9d |
| #7 | Researcher/Backtester/Auditor, queue, registry, UI, optional advisory LLM | 4415383b680d404f8eb9f25df11a6e346ad76bd6 |
| #9 | Chunked storage, controlled errors, offline resource-limited runner | e96a243156b9e978485d0141a2542a4c9b60f27a |

Do not merge both the same stacked changes and this integration independently. This integration PR targets main and replaces the need to merge each source PR separately if it is eventually approved. Review the full main-to-integration diff. No automatic changes to source PR state are made.

## Production invariants and architecture

61 tracked protected files are byte-identical to main, including Auto Paper strategy/execution/service/storage/monitor, Paper, forward validation, patterns, exchange read-only clients, indicators, market providers and requirements. Full hash evidence is in `RESEARCH_INTEGRATION_CODE_AUDIT.json`. `app/main.py` adds only the Research router import/include; its lifespan, scheduler and trading setup are unchanged. Strategy Lab additions stay in the existing isolated Lab namespace. No trading SQL or Supabase schema is changed.

The embedded Research service is permanently read-only; environment role flags cannot arm it. Queue/LLM/recovery mutations return 403. HTTP cannot dispatch a worker, call replay or load the historical dataset. The standalone local Workbench can queue jobs but cannot launch replay over HTTP either. Only an explicit external Linux/WSL CLI runner executes fixed research hypotheses. It does not share the production process, credentials, trading ledger or scheduler. The same existing Lab engine is used; there is no second production trading engine.

Researcher uses curated, sourced hypotheses without an LLM. Backtester and Auditor run deterministic, reproducible calculations in the external runner. With no API configured the actual status is **AI_NOT_CONFIGURED**. LLM advisory remains disabled by default; this integration configures/purchases no provider. No research strategy can automatically activate Paper or real trading.

## Local operation and persistence

Use a separate existing Linux/WSL computer with the complete checkout, pinned requirements and a persistent local directory outside checkout and temporary storage. Configure a **local-only owner password** privately; do not copy production secrets. Keep LLM disabled.

```sh
python -m scripts.research_runner init --state-dir /home/USER/.local/share/aura-research
export AURA_RESEARCH_STATE_DIR=/home/USER/.local/share/aura-research
export AURA_RESEARCH_STORAGE_MODE=durable
export AURA_RESEARCH_LLM_ENABLED=false
# Set AURA_TESTNET_VIEW_PASSWORD securely to a local owner password, >=12 characters.
python -m app.research.web
```

Open `http://127.0.0.1:8001/` and authenticate as owner. Create a job in the UI or explicitly enqueue it:

```sh
python -m scripts.research_runner enqueue --state-dir /home/USER/.local/share/aura-research --hypothesis VOLATILITY_BREAKOUT
python -m scripts.research_runner run --state-dir /home/USER/.local/share/aura-research --job-id JOB_ID --isolated-host
python -m scripts.research_runner verify --state-dir /home/USER/.local/share/aura-research --job-id JOB_ID --isolated-host
python -m scripts.research_runner backup --state-dir /home/USER/.local/share/aura-research --dest /home/USER/backups/aura-NEW
python -m scripts.research_runner restore --backup-dir /home/USER/backups/aura-NEW --state-dir /home/USER/.local/share/aura-restored-NEW
```

Other hypotheses: MEAN_REVERSION, LIQUIDITY_SWEEP, REGIME_SWITCHING. Restart reloads jobs, results and budget history without auto-executing them. Backup/restore verifies chunks and preserves storage identity and budget reservations. Backups must use new destinations, preferably with an off-device copy. Do not operate restored copies concurrently as a global billing counter. v1 prototype research DBs are preserved and rejected with a schema error, not automatically migrated/reset. No trading data migration is required.

The runner uses a process lock, atomic claim/attempt fencing, transactionally saved manifest/chunks/events, a minimal child environment, TCP guards and hard Linux limits. Defaults: 768 MiB address space, 120 CPU seconds, 180 wall seconds, 256 MiB output/DB cap, 64 descriptors, no core dumps, at least 512 MiB disk headroom. These are guards for trusted code, not a hostile-Python sandbox or proof of physical-host separation. Render denies writable runner commands. See `AI_RESEARCH_RELEASE_FIXES.md` for recovery, retention and limits.

## Safe transfer to Render: reviewed immutable Git snapshot

### Options and cost

1. **Implemented, lowest incremental cost:** publish one completed public experiment as verified immutable files in Git. No new service/database/API is required. An existing PC/disk and repository/service quota are still needed. Git's remote history and an offline clone provide durability; Render reconstructs the same snapshot from the checked-out commit after restart/rebuild. A later authorized deploy is required to update it.
2. **Not implemented/provisioned:** private object storage or a verified persistent read-only Render disk with an independent transfer job. This needs infrastructure, retention/access/backup design and may incur storage, egress or instance charges. Current prices/plan compatibility were not verified. Do not configure or purchase this as part of this task.

Use option 1 only when publishing these research results in this **public repository** is acceptable. Private research requires option 2 and further approval. No live uploads, external fetches, webhook or public HTTP write endpoint are added.

### Offline procedure

The export contains only one completed experiment's config, compact result, and compressed record blocks. It excludes the SQLite database, environment, passwords, LLM calls/prompts/usage, queue events and worker logs. Known credential fields/patterns are rejected. Owner review remains required: pattern filtering cannot prove that arbitrary human-supplied text contains no secret. The fixed runner does not receive production/LLM keys.

```sh
# All three commands run LOCALLY, never in the production Render shell.
python -m scripts.research_snapshot export --state-dir /home/USER/.local/share/aura-research --job-id JOB_ID --output /home/USER/exports/aura-NEW
python -m scripts.research_snapshot verify --bundle /home/USER/exports/aura-NEW
# Review files, provenance, privacy and checksum independently before approving publication.
python -m scripts.research_snapshot publish --bundle /home/USER/exports/aura-NEW --checksum CHECKSUM_FROM_REVIEW --owner-approved-publication
```

Export and publish require the configured local owner password via hidden prompt, never a command-line password. Verify needs no password because the bundle contains only public data. Publishing additionally requires an explicit approval flag and matching reviewed checksum. Git write authorization remains separate and is supplied through the owner's normal repository access.

Publish writes only `docs/research-snapshot/` in the local checkout, never an arbitrary destination or trading table. It stages files for review; it **does not commit, push or deploy**. Review/commit/push them on a new branch and request approval before any deployment. No actual result bundle was published by this integration task: the full annual transport exercise used temporary files and retained only small verification evidence.

Only JSON and expected generated chunk filenames are accepted. No supplied paths, SQL, archive extraction or executable payloads are used. Hashes cover the index/manifest, individual raw chunks and complete record sections. The bundle cap is **16 MiB compressed / 128 MiB raw arrays**, index about 516 KiB maximum, chunks 128 KiB raw, at most 2,048 chunks; existing per-record and pagination limits also apply. Unexpected files, links, oversized/missing/corrupted blocks and invalid schemas fail closed. Compressed data is decompressed with a bounded read, including compression-bomb and invalid-deflate checks.

Duplicate destinations/publications are rejected without overwrite. Version 1 permits one active approved snapshot; replacing it requires a deliberate reviewed Git deletion/replacement, retaining the earlier commit as history. An altered bundle cannot silently overwrite it. A checksum establishes integrity, **not authorship or profitability**; independent checksum review and authenticated Git review establish publication authority.

### Render read-only setup after explicit deployment approval

No new Render variable or persistent disk is required for Git mode. The production factory automatically selects `docs/research-snapshot/` if included in the deployed checkout. Do not set writable research storage or start a Workbench/runner on Render. Configuring both an external DB and an approved snapshot fails closed rather than combining stores. Production owner authentication remains the existing `AURA_TESTNET_VIEW_PASSWORD`.

Open `/api/research/login` → `/static/research.html`, refresh and select the snapshot from the results table. Records are owner-only, bounded and read-only. Without an approved snapshot, existing published PR #7 summaries remain available. Research files are not mounted as public static downloads; note that source files in Git are themselves public. Restart/rebuild restores the deployed commit's artifacts; changing runtime ephemeral files is unsupported and unnecessary. Results are not auto-synchronized while research runs locally.

Before an eventual deploy, disable or otherwise control Auto Deploy as needed so pushing/merging cannot trigger an unapproved production rollout. Use staging first, record the exact commit, then verify owner access, disabled mutations, snapshot checksum and terminal/scheduler health. These production steps were **not performed**.

## Tests, review and evidence

Final regression: **1,305 Python tests passed**, zero failures/xfail, one existing Starlette/AnyIO deprecation warning. All **20 offline JavaScript suites passed**. Exact commands and versions are recorded in `RESEARCH_INTEGRATION_TEST_RESULTS.json`. Python tests cover the original strategy/Lab/Paper/monitor suites and additional transport, auth, restart, malformed data, duplicate publication, backup/restore and concurrent Research/virtual-cycle checks. Sandbox-specific select.poll accommodation is invoked only in the test process; no production event-loop change is made.

- `RESEARCH_INTEGRATION_REPRODUCIBILITY.json`: all four real annual experiments, seven runs each, recomputed in the external resource-limited runner on the integration branch. Metrics, trade records, decisions, curves and causal prefix checks match PR #7. Viewer/health requests are exercised during computation. Later acceptance-process RSS baselines include retained reference allocations; they are not clean production memory measurements.
- `RESEARCH_INTEGRATION_TRANSFER_VERIFICATION.json`: actual 36,461,574-byte annual report exported and verified with a fresh reader; 390 files / 1,246,582 bytes including an 86,412-byte index; no database, LLM logs or production access. No publication performed.
- `RESEARCH_INTEGRATION_CODE_AUDIT.json`: source heads, dependency order and 61 unchanged production-file hashes.

The source is Binance Spot BTCUSDT, one coherent annual dataset with UTC 1h/4h aggregation from closed 15m candles. It has already been used for exploratory research, so it is **not a fresh independent validation set**. Strategies remain REJECTED. This release adds no profit claim, parameter search on a new holdout or Paper activation. Existing no-look-ahead tests, causal prefix checks and accounting references remain mandatory.

Explicit code review: dependency diff, factory/read-only interface, snapshot parser, bounded reads, lifecycle, publication/duplicate behavior, SQLite boundaries and error paths were inspected. Security review: owner/CSRF checks, no HTTP importer or executor, generated filenames, path/link rejection, no SQL import/credential export, textContent UI rendering and immutable-source assumptions were inspected. One additional confirmed defect was fixed: a valid gzip header with an invalid deflate body could raise uncaught `zlib.error`; it now maps to RESEARCH_INTEGRITY/503, with a regression test. No known critical/high code finding remains from these passes. External security services or scanners were not invoked; tests are not a penetration-test certification.

The concurrent test runs an existing temporary Auto Paper OPEN/CLOSE cycle alongside Research/health requests and confirms monitor status remains WAITING_FOR_REAL_SIGNAL. It does not write Supabase or claim Render LIVE VERIFIED.

## Remaining gates and manual work

**RELEASE_READY remains FALSE** until an operator completes:

1. Review the complete integration PR and the eventual deployed dependency tree; inspect privacy of any actual snapshot before publication.
2. Verify the chosen machine's real persistent disk, backup/off-device restore, permissions and CPU/memory capacity. Unit/fresh-process tests do not attest the user's hardware or a Render mount.
3. Execute staging acceptance using the eventual deployed commit: owner authorization, disabled Research mutations and worker dispatch, valid/corrupt snapshot handling, restart/rebuild persistence, Strategy Lab, market API, scheduler and existing Paper monitor health under realistic load.
4. Confirm deploy controls and obtain explicit approval. No staging/production Render access or current plan inspection was available here; compatibility under actual service limits is unverified.

These are deployment blockers, not evidence of a failing strategy engine. Optional private-storage infrastructure and automatic multi-experiment synchronization are not supplied. No paid API is needed for deterministic research. Production Aura 4.2 will retain its existing strategy, scheduler, balances, positions, risk limits and Supabase behavior; integration never authorizes trading.

Rollback: preserve external research DB/backups and snapshot Git commits. Revert the complete integration or disable its Research router if needed; do not restore PR #7's old in-web execution route by reverting only safety fixes. Do not downgrade v2 state to v1 or reset any trading ledger. No rollback was executed here.
