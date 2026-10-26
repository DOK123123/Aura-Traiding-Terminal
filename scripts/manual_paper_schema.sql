-- Dedicated Manual Paper v1 only. Prepared for review; never auto-applied.
-- No existing Active43/Auto42/Practice objects are addressed or migrated.
BEGIN;
CREATE TABLE IF NOT EXISTS public.aura_manual_paper_v1_account (
 id integer PRIMARY KEY CHECK(id=1), version bigint NOT NULL CHECK(version>0),
 payload text NOT NULL CHECK(octet_length(payload)<=1048576),
 sha256 text NOT NULL CHECK(sha256=encode(pg_catalog.sha256(convert_to(payload,'UTF8')),'hex')),
 saved_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS public.aura_manual_paper_v1_requests (
 request_id text PRIMARY KEY CHECK(request_id ~ '^[a-f0-9]{32}$'),
 intent_hash text NOT NULL CHECK(intent_hash ~ '^[a-f0-9]{64}$'),
 receipt jsonb NOT NULL CHECK(jsonb_typeof(receipt)='object'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE public.aura_manual_paper_v1_account ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aura_manual_paper_v1_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.aura_manual_paper_v1_account,public.aura_manual_paper_v1_requests FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT,UPDATE ON public.aura_manual_paper_v1_account TO service_role;
GRANT SELECT,INSERT ON public.aura_manual_paper_v1_requests TO service_role;
-- No anon/authenticated policies. service_role is the server-only privileged role.
CREATE OR REPLACE FUNCTION public.aura_manual_paper_v1_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'APPEND_ONLY'; END $$;
DROP TRIGGER IF EXISTS manual_v1_immutable ON public.aura_manual_paper_v1_requests;
CREATE TRIGGER manual_v1_immutable BEFORE UPDATE OR DELETE ON public.aura_manual_paper_v1_requests
FOR EACH ROW EXECUTE FUNCTION public.aura_manual_paper_v1_immutable();

CREATE OR REPLACE FUNCTION public.aura_manual_paper_v1_load(p_known_version bigint DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE r public.aura_manual_paper_v1_account;
BEGIN
 SELECT * INTO r FROM public.aura_manual_paper_v1_account WHERE id=1;
 IF NOT FOUND THEN
  IF EXISTS(SELECT 1 FROM public.aura_manual_paper_v1_requests) THEN
   RETURN jsonb_build_object('error','CORRUPT_JOURNAL');
  END IF;
  RETURN NULL;
 END IF;
 IF r.sha256 IS DISTINCT FROM encode(pg_catalog.sha256(convert_to(r.payload,'UTF8')),'hex') THEN
  RETURN jsonb_build_object('error','CORRUPT_JOURNAL');
 END IF;
 IF p_known_version=r.version THEN
  RETURN jsonb_build_object('scope','AURA_MANUAL_PAPER_V1','version',r.version,'sha256',r.sha256,'unchanged',true);
 END IF;
 RETURN jsonb_build_object('scope','AURA_MANUAL_PAPER_V1','version',r.version,'sha256',r.sha256,'payload',r.payload);
END $$;

CREATE OR REPLACE FUNCTION public.aura_manual_paper_v1_lookup(p_request_id text,p_intent_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE r public.aura_manual_paper_v1_requests;
BEGIN
 IF p_request_id IS NULL OR p_request_id !~ '^[a-f0-9]{32}$' OR p_intent_hash IS NULL OR p_intent_hash !~ '^[a-f0-9]{64}$' THEN
  RETURN jsonb_build_object('error','INVALID_REQUEST_ID');
 END IF;
 SELECT * INTO r FROM public.aura_manual_paper_v1_requests WHERE request_id=p_request_id;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF r.intent_hash IS DISTINCT FROM p_intent_hash THEN RETURN jsonb_build_object('error','IDEMPOTENCY_CONFLICT'); END IF;
 RETURN r.receipt;
END $$;

CREATE OR REPLACE FUNCTION public.aura_manual_paper_v1_commit(
 p_expected_version bigint,p_new_payload text,p_new_sha256 text,
 p_request_id text,p_intent_hash text,p_new_receipt jsonb,p_quote_ms bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' SET statement_timeout='8s' SET lock_timeout='3s' AS $$
DECLARE r public.aura_manual_paper_v1_account; old_request public.aura_manual_paper_v1_requests;
 s jsonb; current_version bigint; age_ms bigint;
BEGIN
 -- A short singleton lock serializes cold start as well as existing accounts.
 -- No network, market fetch, strategy evaluation or sleep occurs under this lock.
 PERFORM pg_advisory_xact_lock(77194357,1);
 IF p_request_id IS NOT NULL THEN
  IF p_request_id !~ '^[a-f0-9]{32}$' OR p_intent_hash IS NULL OR p_intent_hash !~ '^[a-f0-9]{64}$' THEN
   RETURN jsonb_build_object('error','INVALID_REQUEST_ID');
  END IF;
  SELECT * INTO old_request FROM public.aura_manual_paper_v1_requests WHERE request_id=p_request_id;
  IF FOUND THEN
   IF old_request.intent_hash IS DISTINCT FROM p_intent_hash THEN RETURN jsonb_build_object('error','IDEMPOTENCY_CONFLICT'); END IF;
   RETURN old_request.receipt;
  END IF;
 END IF;
 SELECT * INTO r FROM public.aura_manual_paper_v1_account WHERE id=1 FOR UPDATE;
 current_version:=CASE WHEN FOUND THEN r.version ELSE 0 END;
 IF current_version=0 AND EXISTS(SELECT 1 FROM public.aura_manual_paper_v1_requests) THEN
  RETURN jsonb_build_object('error','CORRUPT_JOURNAL');
 END IF;
 IF p_expected_version IS DISTINCT FROM current_version THEN RETURN jsonb_build_object('error','CONCURRENT_UPDATE'); END IF;
 IF p_new_payload IS NULL OR octet_length(p_new_payload)>1048576 OR p_new_sha256 IS DISTINCT FROM encode(pg_catalog.sha256(convert_to(p_new_payload,'UTF8')),'hex') THEN
  RETURN jsonb_build_object('error','WRITE_LIMIT');
 END IF;
 s:=p_new_payload::jsonb;
 IF jsonb_typeof(s) IS DISTINCT FROM 'object' OR s->>'starting_balance' IS DISTINCT FROM '10000'
  OR s->>'fee_rate' IS DISTINCT FROM '0.0006' OR s->>'max_risk' IS DISTINCT FROM '0.005'
  OR s->>'max_notional' IS DISTINCT FROM '2000' OR jsonb_typeof(s->'trades') IS DISTINCT FROM 'array' THEN
  RETURN jsonb_build_object('error','CORRUPT_JOURNAL');
 END IF;
 IF p_request_id IS NULL THEN
  -- Initialization only, never reset/configure an existing account.
  IF current_version<>0 OR p_intent_hash IS NOT NULL OR p_new_receipt IS NOT NULL OR p_quote_ms IS NOT NULL
   OR s->>'balance' IS DISTINCT FROM '10000' OR s->>'realized' IS DISTINCT FROM '0'
   OR s->'position' IS DISTINCT FROM 'null'::jsonb OR s->'trades' IS DISTINCT FROM '[]'::jsonb THEN
   RETURN jsonb_build_object('error','STORAGE_SCOPE_MISMATCH');
  END IF;
 ELSE
  IF jsonb_typeof(p_new_receipt) IS DISTINCT FROM 'object' OR octet_length(p_new_receipt::text)>65536
   OR p_new_receipt->>'request_id' IS DISTINCT FROM p_request_id
   OR ((p_new_receipt->>'command' IS DISTINCT FROM 'OPEN') AND (p_new_receipt->>'command' IS DISTINCT FROM 'CLOSE'))
   OR (p_new_receipt->>'version')::bigint IS DISTINCT FROM current_version+1
   OR p_new_receipt->>'balance' IS DISTINCT FROM s->>'balance'
   OR jsonb_typeof(p_new_receipt->'result') IS DISTINCT FROM 'object' THEN
   RETURN jsonb_build_object('error','CORRUPT_JOURNAL');
  END IF;
  -- Database clock is evaluated AFTER lock wait, including network/queue delay.
  age_ms:=floor(extract(epoch FROM clock_timestamp())*1000)::bigint-p_quote_ms;
  IF p_quote_ms IS NULL OR age_ms NOT BETWEEN 0 AND 5000 THEN RETURN jsonb_build_object('error','STALE_QUOTE'); END IF;
 END IF;
 IF current_version=0 THEN
  INSERT INTO public.aura_manual_paper_v1_account(id,version,payload,sha256)
   VALUES(1,1,p_new_payload,p_new_sha256);
 ELSE
  UPDATE public.aura_manual_paper_v1_account SET version=current_version+1,payload=p_new_payload,
   sha256=p_new_sha256,saved_at=clock_timestamp() WHERE id=1;
 END IF;
 IF p_request_id IS NOT NULL THEN
  INSERT INTO public.aura_manual_paper_v1_requests(request_id,intent_hash,receipt)
   VALUES(p_request_id,p_intent_hash,p_new_receipt);
  RETURN p_new_receipt;
 END IF;
 RETURN jsonb_build_object('version',1);
END $$;
REVOKE ALL ON FUNCTION public.aura_manual_paper_v1_immutable() FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.aura_manual_paper_v1_load(bigint) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.aura_manual_paper_v1_lookup(text,text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.aura_manual_paper_v1_commit(bigint,text,text,text,text,jsonb,bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.aura_manual_paper_v1_load(bigint) TO service_role;
GRANT EXECUTE ON FUNCTION public.aura_manual_paper_v1_lookup(text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.aura_manual_paper_v1_commit(bigint,text,text,text,text,jsonb,bigint) TO service_role;
COMMIT;
