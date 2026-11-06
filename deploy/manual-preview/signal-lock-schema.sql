-- REVIEW ONLY. Do not apply without the owner-approved preview DB change.
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
 RETURN n=1;
END $$;
REVOKE ALL ON FUNCTION public.aura_preview_lock_load_v1() FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.aura_preview_lock_commit_v1(bigint,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.aura_preview_lock_load_v1() TO service_role;
GRANT EXECUTE ON FUNCTION public.aura_preview_lock_commit_v1(bigint,jsonb) TO service_role;
COMMIT;
