"""Disposable local SQL-only preview verification. Never hosted Supabase."""
import json,os,uuid
from scripts.verify_manual_paper_postgres import PG,SQLStore,wait,DATABASE
from scripts.verify_practice_postgres import docker,IMAGE
from scripts.build_manual_preview_sql import rendered
from app.manual_paper.commands import ManualCommands
from scripts.verify_manual_paper_postgres import quote

REF='abcdefghijklmnopqrst'

def verify(pg):
    checks=[]
    pg.sql('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;')
    # Unsafe target aborts the ENTIRE pack before creating even the scope marker.
    pg.sql('CREATE TABLE public.production_sentinel(balance numeric); INSERT INTO public.production_sentinel VALUES(10000);')
    r=pg.sql(rendered(REF),check=False)
    assert r.returncode!=0 and 'PREVIEW_EMPTY_PROJECT_REQUIRED' in r.stderr
    assert pg.sql("SELECT to_regclass('public.aura_manual_preview_scope') IS NULL;")=='t'
    assert pg.sql('SELECT balance FROM public.production_sentinel;')=='10000'
    pg.sql('DROP TABLE public.production_sentinel;');checks.append('NONEMPTY_TARGET_REFUSED_NO_PRODUCTION_BALANCE_CHANGE')
    pg.sql(rendered(REF));pg.sql(rendered(REF));checks.append('FRESH_SCHEMA_AND_REAPPLY')
    for role in ['anon','authenticated']:
        output=pg.sql('SELECT public.aura_manual_preview_guard();',role=role,check=False)
        assert output.returncode!=0 and 'permission denied' in output.stderr.lower()
    checks.append('ANON_AUTHENTICATED_NO_GUARD_ACCESS')
    claims=json.dumps({'role':'service_role','ref':REF})
    v=pg.sql("SET request.jwt.claims = '"+claims+"'; SELECT public.aura_manual_preview_guard();",role='service_role')
    parsed=json.loads(v);assert parsed['isolated'] is True and parsed['project_ref']==REF;checks.append('SERVICE_ROLE_READ_ONLY_ATTESTATION')
    s=SQLStore(pg);cmd=ManualCommands(s)
    cmd.open('a'*32,'LONG','0.01','79500','81000',quote());before=s.load()[0].balance
    pg.restart();restored=SQLStore(pg);assert restored.load()[0].position.id=='a'*32 and restored.load()[0].balance==before
    ManualCommands(restored).close('b'*32,quote('81000'),'a'*32)
    assert len(restored.load()[0].trades)==1;checks.append('OPEN_CLOSE_AND_DATABASE_RESTART')
    payload=pg.sql('SELECT payload FROM public.aura_manual_paper_v1_account;');pg.sql(rendered(REF));assert payload==pg.sql('SELECT payload FROM public.aura_manual_paper_v1_account;');checks.append('REAPPLY_PRESERVES_LEDGER')
    pg.sql('CREATE TABLE public.foreign_account(id int);')
    v=json.loads(pg.sql("SET request.jwt.claims = '"+claims+"'; SELECT public.aura_manual_preview_guard();",role='service_role'));assert v['isolated'] is False;checks.append('FOREIGN_TABLE_REVOKES_ATTESTATION')
    return dict(status='PASS',checks=checks,production_changed=False,hosted_supabase_verified=False)

def run():
    if os.getenv('RENDER'):raise ValueError('LOCAL_DISPOSABLE_ONLY')
    name='aura-manual-pg-'+uuid.uuid4().hex[:12]
    docker('run','-d','--name',name,'--label','aura.manual.verification=true','--network','none','--memory','512m','--cpus','1','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB='+DATABASE,IMAGE)
    try:wait(name);return verify(PG(name))
    finally:docker('rm','-fv',name,check=False)
if __name__=='__main__':print(json.dumps(run()))
