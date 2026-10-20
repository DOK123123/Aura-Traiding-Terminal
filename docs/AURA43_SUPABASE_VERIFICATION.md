# Aura 4.3 Bitget: production Supabase verification, 2026-10-20

## Concrete production result

[Diagnostic run #8](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/39380544587)
was dispatched from this branch using only the read-only diagnostic endpoint.
It returned:

```json
{"status":"BLOCKED","bitget":"CONNECTED","supabase":"ERROR",
 "supabase_code":"INVALID_STORAGE_CONFIGURATION",
 "supabase_history_rpc_verified":false,"supabase_account_read_verified":false,
 "scheduler":"ERROR","scheduler_code":"NO_CONFIRMED_TICK",
 "state_changed":false,"production_paper_verified":false}
```

**Supabase failed during client configuration validation, before any HTTP/RPC.**
The deployed transport accepts only an HTTPS project URL matching
`https://[a-z0-9]{12,40}.supabase.co` and a printable ASCII key of 32–8192 characters.
The old shared error does not identify which of these input validations failed.
No inference about secret values is made. The currently reported failure is not
an RPC execution or RLS failure: those stages have not been reached.

No database writes, portfolio initialization, scheduler tick, mode change, secret
change or exchange order were performed by this diagnostic. Authorization worked
and Bitget was CONNECTED from the actual Render diagnostic request.

## Code corrections

- Dedicated validator reports `STORAGE_URL_MISSING`, `STORAGE_URL_INVALID`,
  `STORAGE_KEY_MISSING`, `STORAGE_KEY_INVALID` instead of the ambiguous error.
- Harmless surrounding whitespace and trailing root slashes in the URL are
  normalized. Key copy/paste whitespace at the edges is normalized in memory.
  Saved secrets are not modified. Internal line breaks remain invalid. No
  alternative project, provider, generic env fallback, custom host or insecure
  connection is allowed.
- Owner diagnostics includes only names, validity and normalization flags, never
  a URL/key value, length or fingerprint. Actions prints whitelisted codes and
  read-verification flags, not raw upstream data.
- Explicit stages: CONFIGURATION → HISTORY_RPC → ACCOUNT_READ → STATE_VALIDATION
  → COMPLETE. A failure retains its actual stage.
- **Scheduler diagnosis fixed:** failed DB reads cannot establish the absence of
  ticks. New code is `SCHEDULER_STORAGE_UNVERIFIED`, not `NO_CONFIRMED_TICK`.
  An absent account has `SCHEDULER_ACCOUNT_NOT_INITIALIZED`. Only a successfully
  read account can produce NO_CONFIRMED_TICK, STALE_TICK or ACTIVE.
- Owner Panel has Russian messages for these errors. Nothing enables PAPER.

## RPC, SQL and Render variable correspondence

| Component | Exact expected name/signature |
| --- | --- |
| Project URL | `AURA_ACTIVE43_BITGET_SUPABASE_URL` |
| Server key | `AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY` |
| Portfolio read/init RPC | `public.aura_active43_bitget_load(seed jsonb)` |
| Atomic persistence RPC | `public.aura_active43_bitget_commit(expected_revision bigint,new_state jsonb,new_events jsonb,operation_key text)` |
| Diagnostic history RPC | `public.aura_active43_bitget_history(selected_epoch text,after_seq bigint,row_limit integer,event_id text,kind_filter text,before_seq bigint)` |
| Read-only account | `public.aura_active43_bitget_account`, fields `revision,payload,sha256,saved_at`, id=1 |
| Migration | `scripts/active43_bitget_schema.sql` |

Python argument names/types match the migration. RLS denies anon/authenticated;
only service_role executes these RPCs. SELECT account grant is in that migration
and in the existing optional `active43_bitget_diagnostics_grant.sql`.
No SQL change or production SQL application is needed for the proven current
**configuration** failure. Hosted RPC presence/grants cannot yet be confirmed:
the Render client did not reach Supabase. Local PostgreSQL results are reported
separately, not represented as hosted verification.

## Minimal owner procedure

1. Review/publish this PR, keeping PAPER and the external scheduler opt-in OFF.
   On Render, deploy the reviewed main with existing saved environment. This
   agent did not merge/deploy or change any setting.
2. Run [Actions → Aura 4.3 → Run workflow → diagnostics](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/workflows/aura-active43.yml).
   Normalizable copy/paste padding is fixed automatically. Otherwise the exact
   variable is identified by STORAGE_URL_INVALID or STORAGE_KEY_INVALID.
3. Only if still invalid, in [Render Environment](https://dashboard.render.com/)
   correct the named existing variable and apply the saved environment:
   - `AURA_ACTIVE43_BITGET_SUPABASE_URL`: project API root such as
     `https://PROJECT_REF.supabase.co`, not dashboard URL, project ref alone,
     `/rest/v1`, PostgreSQL DSN or a database password.
   - `AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY`: existing server service_role API
     key for that same project, not anon/publishable key or database password.
     Never put the value into chat or logs. No new key is needed.

Then repeat diagnostics. Expect `supabase=CONNECTED`, `supabase_code=null`,
`supabase_stage=COMPLETE`, both read-verification flags true. If there is no
portfolio yet, NOT_INITIALIZED is honest and read-only diagnostics will not create
one. Opening the normal owner portfolio view uses the existing load/init path,
which initializes a new isolated OFF account at 10000 and does not reset existing
accounts. No account initialization was performed in this session.

Scheduler can legitimately remain NO_CONFIRMED_TICK while external scheduling is
OFF. Diagnostic delivery is not a persisted trading tick. Do not enable PAPER to
make this status green. Enabling external ticks later is a separate owner decision.

## Optional read-only SQL inspection (not required for current error)

Only after a schema error at HISTORY_RPC/ACCOUNT_READ, these read-only commands
can inspect the existing project without touching data:

```sql
SELECT to_regclass('public.aura_active43_bitget_account') AS account_table,
       to_regclass('public.aura_active43_bitget_events') AS events_table;
SELECT to_regprocedure('public.aura_active43_bitget_load(jsonb)') AS load_rpc,
       to_regprocedure('public.aura_active43_bitget_commit(bigint,jsonb,jsonb,text)') AS commit_rpc,
       to_regprocedure('public.aura_active43_bitget_history(text,bigint,integer,text,text,bigint)') AS history_rpc;
```

No automatic migration, broad grants, resets, old Bybit schema reuse or changes to
Aura 4.2/Paper Practice are proposed. Actual tests and explicit code/security review
are recorded in `AURA43_SUPABASE_RESULTS.json`.
