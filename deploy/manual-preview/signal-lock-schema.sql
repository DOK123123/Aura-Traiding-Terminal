-- Dedicated Preview Signal Lock. Does not modify existing PAPER tables/guard.
-- Run under the dedicated Preview project, never the production project.
BEGIN;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM public.aura_manual_preview_scope
                WHERE id=1 AND scope='AURA_MANUAL_PREVIEW_ONLY_V1'
                AND project_ref='kkxdftdojvnsjqlrulpb') THEN
  RAISE EXCEPTION 'DEDICATED_PREVIEW_SCOPE_REQUIRED';
 END IF;
END $$;
-- Separate schema leaves every existing PAPER table and its guard unchanged.
CREATE SCHEMA IF NOT EXISTS aura_preview_signals;
REVOKE ALL ON SCHEMA aura_preview_signals FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA aura_preview_signals TO service_role;
CREATE TABLE IF NOT EXISTS aura_preview_signals.lock_state_v1 (
 id boolean PRIMARY KEY DEFAULT true CHECK(id),
 version bigint NOT NULL DEFAULT 0,
 state jsonb NOT NULL DEFAULT '{"events":{},"notices":{},"cooldowns":{}}'::jsonb
);
CREATE TABLE IF NOT EXISTS aura_preview_signals.event_archive_v1 (
 id text PRIMARY KEY CHECK(id ~ '^[a-f0-9]{64}$'), payload jsonb NOT NULL,
 detected_at double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS signal_archive_time ON aura_preview_signals.event_archive_v1(detected_at DESC,id);
ALTER TABLE aura_preview_signals.event_archive_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON aura_preview_signals.event_archive_v1 FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON aura_preview_signals.event_archive_v1 TO service_role;
ALTER TABLE aura_preview_signals.lock_state_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON aura_preview_signals.lock_state_v1 FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON aura_preview_signals.lock_state_v1 TO service_role;
INSERT INTO aura_preview_signals.lock_state_v1(id) VALUES(true) ON CONFLICT DO NOTHING;
CREATE OR REPLACE FUNCTION public.aura_preview_lock_load_v1() RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT jsonb_build_object('version',version,'state',state)
 FROM aura_preview_signals.lock_state_v1 WHERE id=true;
$$;
CREATE OR REPLACE FUNCTION public.aura_preview_lock_commit_v1(p_version bigint,p_state jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE n int;
BEGIN
 IF jsonb_typeof(p_state) IS DISTINCT FROM 'object' OR jsonb_typeof(p_state->'events') IS DISTINCT FROM 'object'
    OR jsonb_typeof(p_state->'notices') IS DISTINCT FROM 'object' OR jsonb_typeof(p_state->'cooldowns') IS DISTINCT FROM 'object'
    OR octet_length(p_state::text)>4000000 THEN RAISE EXCEPTION 'LOCK_STATE_FORMAT'; END IF;
 UPDATE aura_preview_signals.lock_state_v1 SET version=version+1,state=p_state
 WHERE id=true AND version=p_version;
 GET DIAGNOSTICS n=ROW_COUNT;
 IF n=1 THEN
  INSERT INTO aura_preview_signals.event_archive_v1(id,payload,detected_at)
   SELECT key,value,(value->>'detected_at')::double precision FROM jsonb_each(p_state->'events')
   ON CONFLICT(id) DO UPDATE SET payload=excluded.payload
    WHERE aura_preview_signals.event_archive_v1.payload IS DISTINCT FROM excluded.payload;
 END IF;
 RETURN n=1;
END $$;
REVOKE ALL ON FUNCTION public.aura_preview_lock_load_v1() FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.aura_preview_lock_commit_v1(bigint,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.aura_preview_lock_load_v1() TO service_role;
GRANT EXECUTE ON FUNCTION public.aura_preview_lock_commit_v1(bigint,jsonb) TO service_role;
CREATE OR REPLACE FUNCTION public.aura_preview_lock_history_v1(p_before double precision,p_frame text DEFAULT NULL,p_limit int DEFAULT 50,p_before_id text DEFAULT 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff') RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT coalesce(jsonb_agg(payload ORDER BY detected_at DESC,id DESC),'[]'::jsonb) FROM
  (SELECT id,payload,detected_at FROM aura_preview_signals.event_archive_v1
   WHERE (detected_at,id)<(p_before,p_before_id) AND (p_frame IS NULL OR payload->>'frame'=p_frame)
   ORDER BY detected_at DESC,id DESC LIMIT least(greatest(p_limit,1),100)) rows;
$$;
REVOKE ALL ON FUNCTION public.aura_preview_lock_history_v1(double precision,text,int,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.aura_preview_lock_history_v1(double precision,text,int,text) TO service_role;
CREATE OR REPLACE FUNCTION public.aura_preview_lock_event_v1(p_id text) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT payload FROM aura_preview_signals.event_archive_v1 WHERE id=p_id;
$$;
REVOKE ALL ON FUNCTION public.aura_preview_lock_event_v1(text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.aura_preview_lock_event_v1(text) TO service_role;
COMMIT;
