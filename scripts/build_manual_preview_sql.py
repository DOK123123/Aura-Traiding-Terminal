"""Offline SQL packager; never connects or applies migrations."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
PREFIX='''-- Dedicated EMPTY Supabase PREVIEW project only. Never production.
-- Generated from existing manual schema plus isolation guards; no deploy hook.
BEGIN;
SET LOCAL aura.preview_project_ref = 'REPLACE_PREVIEW_PROJECT_REF';
DO $$
BEGIN
 IF current_setting('aura.preview_project_ref') !~ '^[a-z0-9]{20}$' OR current_setting('aura.preview_project_ref')='uvcbhicbnqpqobxnufph' THEN
  RAISE EXCEPTION 'PREVIEW_PROJECT_REF_REQUIRED_OR_FORBIDDEN';
 END IF;
 IF to_regclass('public.aura_manual_preview_scope') IS NULL THEN
  IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f'))
    OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='public' AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')) THEN
   RAISE EXCEPTION 'PREVIEW_EMPTY_PROJECT_REQUIRED';
  END IF;
 ELSE
  IF NOT EXISTS(SELECT 1 FROM public.aura_manual_preview_scope WHERE id=1 AND scope='AURA_MANUAL_PREVIEW_ONLY_V1' AND project_ref=current_setting('aura.preview_project_ref')) THEN
   RAISE EXCEPTION 'PREVIEW_SCOPE_MISMATCH';
  END IF;
  IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f')
              AND c.relname NOT IN ('aura_manual_preview_scope','aura_manual_paper_v1_account','aura_manual_paper_v1_requests')) THEN
   RAISE EXCEPTION 'PREVIEW_FOREIGN_TABLES';
  END IF;
 END IF;
END $$;
'''
SUFFIX='''
CREATE TABLE IF NOT EXISTS public.aura_manual_preview_scope (
 id int PRIMARY KEY CHECK(id=1), project_ref text NOT NULL CHECK(project_ref ~ '^[a-z0-9]{20}$'), scope text NOT NULL CHECK(scope='AURA_MANUAL_PREVIEW_ONLY_V1')
);
INSERT INTO public.aura_manual_preview_scope VALUES(1,current_setting('aura.preview_project_ref'),'AURA_MANUAL_PREVIEW_ONLY_V1') ON CONFLICT(id) DO NOTHING;
ALTER TABLE public.aura_manual_preview_scope ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.aura_manual_preview_scope FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.aura_manual_preview_scope TO service_role;
CREATE OR REPLACE FUNCTION public.aura_manual_preview_guard() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE claims jsonb; isolated boolean;
BEGIN
 claims:=coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb;
 isolated:=EXISTS(SELECT 1 FROM public.aura_manual_preview_scope WHERE id=1 AND scope='AURA_MANUAL_PREVIEW_ONLY_V1')
 AND NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f')
   AND c.relname NOT IN ('aura_manual_preview_scope','aura_manual_paper_v1_account','aura_manual_paper_v1_requests'));
 RETURN jsonb_build_object('scope','AURA_MANUAL_PREVIEW_ONLY_V1',
   'project_ref',(SELECT project_ref FROM public.aura_manual_preview_scope WHERE id=1),'role',current_user,
   'isolated',isolated AND current_user='service_role' AND claims->>'role'='service_role');
END $$;
REVOKE ALL ON FUNCTION public.aura_manual_preview_guard() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.aura_manual_preview_guard() TO service_role;
COMMIT;
'''

def rendered(project_ref="REPLACE_PREVIEW_PROJECT_REF"):
    if project_ref!='REPLACE_PREVIEW_PROJECT_REF' and (not re.fullmatch('[a-z0-9]{20}',project_ref) or project_ref=='uvcbhicbnqpqobxnufph'):raise ValueError('PREVIEW_PROJECT_FORBIDDEN')
    source=(ROOT/'scripts/manual_paper_schema.sql').read_text()
    if source.count('BEGIN;')!=1 or source.count('COMMIT;')!=1:raise ValueError('MANUAL_SCHEMA_STRUCTURE_CHANGED')
    return PREFIX.replace('REPLACE_PREVIEW_PROJECT_REF',project_ref)+source.replace('BEGIN;','').replace('COMMIT;','')+SUFFIX

if __name__=='__main__':
    (ROOT/'deploy/manual-preview/schema.sql').write_text(rendered())
