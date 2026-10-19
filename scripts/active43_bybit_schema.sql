-- New isolated Bybit Futures virtual portfolio only. Existing Spot schema is untouched. Apply manually; never resets other accounts.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;
CREATE TABLE IF NOT EXISTS public.aura_active43_bybit_account(
 id integer PRIMARY KEY CHECK(id=1),revision bigint NOT NULL,payload text NOT NULL,sha256 text NOT NULL,saved_at timestamptz NOT NULL);
CREATE TABLE IF NOT EXISTS public.aura_active43_bybit_events(
 seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,id text UNIQUE NOT NULL,epoch text NOT NULL,kind text NOT NULL,
 created_at bigint NOT NULL,payload text NOT NULL,sha256 text NOT NULL,ingested_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE INDEX IF NOT EXISTS aura_active43_bybit_epoch ON public.aura_active43_bybit_events(epoch,seq);
CREATE INDEX IF NOT EXISTS aura_active43_bybit_trades ON public.aura_active43_bybit_events(epoch,seq DESC) WHERE kind='CLOSE';
ALTER TABLE public.aura_active43_bybit_account ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aura_active43_bybit_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.aura_active43_bybit_account,public.aura_active43_bybit_events FROM PUBLIC,anon,authenticated;
REVOKE ALL ON SEQUENCE public.aura_active43_bybit_events_seq_seq FROM PUBLIC,anon,authenticated;
CREATE OR REPLACE FUNCTION public.aura_active43_bybit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'APPEND_ONLY'; END $$;
DROP TRIGGER IF EXISTS aura_active43_bybit_immutable ON public.aura_active43_bybit_events;
CREATE TRIGGER aura_active43_bybit_immutable BEFORE UPDATE OR DELETE ON public.aura_active43_bybit_events FOR EACH ROW EXECUTE FUNCTION public.aura_active43_bybit_immutable();

CREATE OR REPLACE FUNCTION public.aura_active43_bybit_now() RETURNS bigint LANGUAGE sql VOLATILE SET search_path=pg_catalog AS $$ SELECT floor(extract(epoch FROM clock_timestamp()))::bigint $$;
REVOKE ALL ON FUNCTION public.aura_active43_bybit_now() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.aura_active43_bybit_load(seed jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,extensions,pg_temp AS $$
DECLARE s jsonb;r public.aura_active43_bybit_account;
BEGIN
 s:=(seed->>'payload')::jsonb;
 IF seed->>'sha256' IS DISTINCT FROM encode(extensions.digest(convert_to(seed->>'payload','UTF8'),'sha256'),'hex')
  OR s->>'scope' IS DISTINCT FROM 'AURA43_ACTIVE_PAPER' OR s->>'strategy_version' IS DISTINCT FROM 'AURA_4.3_ACTIVE_PAPER_2'
  OR s->>'market_source' IS DISTINCT FROM 'Bybit · USDT Perpetual / api.bybit.com'
  OR s->'market_identity' IS DISTINCT FROM '{"exchange":"BYBIT","market_type":"USDT_PERPETUAL","category":"linear","symbol":"BTCUSDT","settlement":"USDT"}'::jsonb
  OR s->>'mode' IS DISTINCT FROM 'OFF' OR s->>'balance' IS DISTINCT FROM '10000' OR s->>'equity' IS DISTINCT FROM '10000'
  OR s->'position' IS DISTINCT FROM 'null'::jsonb OR s->>'epoch' IS NULL OR left(s->>'epoch',15) IS DISTINCT FROM 'ACTIVE43_BYBIT_' THEN
  RETURN jsonb_build_object('error','CORRUPT_PORTFOLIO'); END IF;
 INSERT INTO public.aura_active43_bybit_account VALUES(1,1,seed->>'payload',seed->>'sha256',clock_timestamp()) ON CONFLICT DO NOTHING;
 SELECT * INTO r FROM public.aura_active43_bybit_account WHERE id=1;
 RETURN jsonb_build_object('revision',r.revision,'payload',r.payload,'sha256',r.sha256,'last_saved_at',floor(extract(epoch FROM r.saved_at))::bigint);
EXCEPTION WHEN invalid_text_representation THEN RETURN jsonb_build_object('error','CORRUPT_PORTFOLIO');
END $$;

CREATE OR REPLACE FUNCTION public.aura_active43_bybit_commit(expected_revision bigint,new_state jsonb,new_events jsonb,operation_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,extensions,pg_temp AS $$
DECLARE s jsonb;old_s jsonb;r public.aura_active43_bybit_account;e jsonb;p jsonb;step bigint;checked_now bigint;
BEGIN
 SELECT * INTO r FROM public.aura_active43_bybit_account WHERE id=1 FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','CORRUPT_PORTFOLIO'); END IF;
 IF EXISTS(SELECT 1 FROM public.aura_active43_bybit_events WHERE id=operation_key) THEN
  RETURN jsonb_build_object('revision',r.revision,'payload',r.payload,'sha256',r.sha256,'last_saved_at',floor(extract(epoch FROM r.saved_at))::bigint,'duplicate',true); END IF;
 IF expected_revision IS DISTINCT FROM r.revision THEN RETURN jsonb_build_object('error','CONCURRENT_UPDATE'); END IF;
 IF jsonb_typeof(new_events) IS DISTINCT FROM 'array' OR jsonb_array_length(new_events) NOT BETWEEN 1 AND 100
  OR octet_length(new_state->>'payload') IS NULL OR octet_length(new_state->>'payload')>65536 THEN RETURN jsonb_build_object('error','WRITE_LIMIT'); END IF;
 s:=(new_state->>'payload')::jsonb;old_s:=r.payload::jsonb;
 IF new_state->>'sha256' IS DISTINCT FROM encode(extensions.digest(convert_to(new_state->>'payload','UTF8'),'sha256'),'hex')
  OR s->>'scope' IS DISTINCT FROM 'AURA43_ACTIVE_PAPER' OR s->>'strategy_version' IS DISTINCT FROM 'AURA_4.3_ACTIVE_PAPER_2'
  OR s->>'market_source' IS DISTINCT FROM 'Bybit · USDT Perpetual / api.bybit.com'
  OR s->'market_identity' IS DISTINCT FROM '{"exchange":"BYBIT","market_type":"USDT_PERPETUAL","category":"linear","symbol":"BTCUSDT","settlement":"USDT"}'::jsonb
  OR s->>'epoch' IS DISTINCT FROM old_s->>'epoch' OR s->>'mode' IS NULL OR s->>'mode' NOT IN ('OFF','ON','PAUSED','ERROR','EMERGENCY') THEN RETURN jsonb_build_object('error','CORRUPT_PORTFOLIO'); END IF;
 IF s->'config' IS DISTINCT FROM old_s->'config' OR s->>'config_hash' IS DISTINCT FROM old_s->>'config_hash'
  OR s->>'active_policy_hash' IS DISTINCT FROM old_s->>'active_policy_hash' OR s->>'policy_hash' IS DISTINCT FROM old_s->>'policy_hash' OR s->>'version' IS DISTINCT FROM old_s->>'version' THEN RETURN jsonb_build_object('error','CONFIG_CHANGED'); END IF;
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(new_events) x WHERE x->>'id'=operation_key) THEN RETURN jsonb_build_object('error','INVALID_EVENT'); END IF;
 -- Protective exits may catch up; new OPEN must still be current when the DB
 -- transaction actually acquires the lock, including an uncertain HTTP timeout.
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(new_events) x WHERE x->>'kind'='OPEN') THEN
  step:=CASE s->'config'->>'timeframe' WHEN '5m' THEN 300 WHEN '15m' THEN 900 WHEN '1h' THEN 3600 WHEN '4h' THEN 14400 ELSE 0 END;
  checked_now:=public.aura_active43_bybit_now();
  IF step=0 OR old_s->>'mode' IS DISTINCT FROM 'ON' OR (s->>'watermark')::bigint IS DISTINCT FROM (checked_now/step)*step
     OR s->>'last_run_at' IS NULL OR abs(checked_now-(s->>'last_run_at')::bigint)>20 THEN
    RETURN jsonb_build_object('error','STALE_EXECUTION_AT_COMMIT'); END IF;
 END IF;

 FOR e IN SELECT * FROM jsonb_array_elements(new_events) LOOP
  p:=(e->>'payload')::jsonb;
  IF octet_length(e->>'payload') IS NULL OR octet_length(e->>'payload')>65536 OR length(e->>'id')>200
    OR e->>'id' IS NULL OR e->>'id' IS DISTINCT FROM p->>'id' OR e->>'epoch' IS DISTINCT FROM s->>'epoch'
    OR p->>'epoch' IS DISTINCT FROM s->>'epoch' OR e->>'kind' IS DISTINCT FROM p->>'kind'
    OR p->'payload'->>'scope' IS DISTINCT FROM 'AURA43_ACTIVE_PAPER'
    OR p->'payload'->>'execution_mode' IS DISTINCT FROM 'PAPER_ONLY'
    OR p->'payload'->>'real_money_execution' IS DISTINCT FROM 'DISABLED'
    OR e->>'sha256' IS DISTINCT FROM encode(extensions.digest(convert_to(e->>'payload','UTF8'),'sha256'),'hex') THEN
      RAISE EXCEPTION 'INVALID_EVENT'; END IF;
  INSERT INTO public.aura_active43_bybit_events(id,epoch,kind,created_at,payload,sha256) VALUES(e->>'id',e->>'epoch',e->>'kind',(e->>'created_at')::bigint,e->>'payload',e->>'sha256');
 END LOOP;
 UPDATE public.aura_active43_bybit_account SET revision=revision+1,payload=new_state->>'payload',sha256=new_state->>'sha256',saved_at=clock_timestamp() WHERE id=1 RETURNING * INTO r;
 RETURN jsonb_build_object('revision',r.revision,'payload',r.payload,'sha256',r.sha256,'last_saved_at',floor(extract(epoch FROM r.saved_at))::bigint,'duplicate',false);
EXCEPTION WHEN data_exception OR integrity_constraint_violation OR raise_exception THEN RETURN jsonb_build_object('error','INVALID_EVENT');
END $$;

CREATE OR REPLACE FUNCTION public.aura_active43_bybit_history(selected_epoch text DEFAULT NULL,after_seq bigint DEFAULT NULL,row_limit integer DEFAULT 50,event_id text DEFAULT NULL,kind_filter text DEFAULT NULL,before_seq bigint DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE result jsonb;
BEGIN
 IF row_limit IS NULL OR row_limit NOT BETWEEN 1 AND 200 OR (kind_filter IS NOT NULL AND kind_filter NOT IN ('CLOSE','OPEN','SIGNAL','ERROR')) THEN RETURN jsonb_build_object('error','WRITE_LIMIT'); END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY CASE WHEN after_seq IS NULL THEN -seq ELSE seq END),'[]'::jsonb) INTO result
 FROM (SELECT seq,payload,sha256 FROM public.aura_active43_bybit_events
  WHERE (selected_epoch IS NULL OR epoch=selected_epoch) AND (event_id IS NULL OR id=event_id)
   AND (after_seq IS NULL OR seq>after_seq) AND (before_seq IS NULL OR seq<before_seq)
   AND (kind_filter IS NULL OR kind=kind_filter)
  ORDER BY CASE WHEN after_seq IS NULL THEN -seq ELSE seq END LIMIT row_limit) t;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.aura_active43_bybit_immutable() FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.aura_active43_bybit_load(jsonb) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.aura_active43_bybit_commit(bigint,jsonb,jsonb,text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.aura_active43_bybit_history(text,bigint,integer,text,text,bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.aura_active43_bybit_load(jsonb),public.aura_active43_bybit_commit(bigint,jsonb,jsonb,text),public.aura_active43_bybit_history(text,bigint,integer,text,text,bigint) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
