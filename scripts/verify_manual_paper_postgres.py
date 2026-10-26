"""Real disposable PostgreSQL tests, no hosted database/keys/real quotes.

Only a labelled Docker container via local Unix socket, network=none. Production
Store and Commands run unchanged; rpc is adapted to real psql (not PostgREST).
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from scripts.verify_practice_postgres import docker,IMAGE
from app.manual_paper.commands import ManualCommands
from app.manual_paper.core import ManualPaper
from app.manual_paper.supabase_store import SupabaseStore,PREFIX

ROOT=Path(__file__).resolve().parents[1]
DATABASE='aura_manual_paper_verification'


class PG:
    def __init__(self,container):
        if not re.fullmatch(r'aura-manual-pg-[a-f0-9]{12}',container):raise ValueError('DISPOSABLE_ONLY')
        labels=json.loads(docker('inspect','--format','{{json .Config.Labels}}',container).stdout)
        network=docker('inspect','--format','{{.HostConfig.NetworkMode}}',container).stdout.strip()
        if labels.get('aura.manual.verification')!='true' or network!='none':raise ValueError('DISPOSABLE_ONLY')
        self.container=container
    def sql(self,sql,role='postgres',check=True):
        if role not in ('postgres','service_role','anon','authenticated'):raise ValueError('INVALID_ROLE')
        r=docker('exec','-i',self.container,'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','postgres','-d',DATABASE,
                 input='SET ROLE '+role+';\n'+sql,check=check)
        return r.stdout.strip() if check else r
    def rpc(self,name,args):
        expressions={
            'load':"(a->>'known_version')::bigint",
            'lookup':"a->>'request_id',a->>'intent_hash'",
            'commit':"(a->>'expected_version')::bigint,a->>'new_payload',a->>'new_sha256',a->>'request_id',a->>'intent_hash',nullif(a->'new_receipt','null'::jsonb),(a->>'quote_ms')::bigint",
        }
        if name not in expressions:raise ValueError('STORAGE_SCOPE_MISMATCH')
        raw=base64.b64encode(json.dumps(args).encode()).decode()
        sql="WITH arg AS (SELECT convert_from(decode('"+raw+"','base64'),'UTF8')::jsonb a) SELECT public."+PREFIX+name+'('+expressions[name]+') FROM arg;'
        raw_result=self.sql(sql,'service_role')
        result=json.loads(raw_result) if raw_result else None
        if isinstance(result,dict) and result.get('error'):raise ValueError(result['error'])
        return result
    def restart(self):
        docker('restart',self.container)
        wait(self.container)


class SQLStore(SupabaseStore):
    def __init__(self,pg):
        import threading
        self.pg=pg;self.cache_lock=threading.Lock();self.cached=None
    def rpc(self,name,args):return self.pg.rpc(name,args)
    def close(self):pass


def wait(container):
    for _ in range(100):
        if docker('exec',container,'pg_isready','-h','127.0.0.1','-U','postgres','-d',DATABASE,check=False).returncode==0:return
        time.sleep(.1)
    raise RuntimeError('PG_STARTUP_TIMEOUT')


def quote(price='80000'):
    return dict(source='Bitget USDT-M Futures',price=price,time=int(time.time()*1000)-20)


def verify(pg):
    from decimal import Decimal
    checks=[]
    def passed(name):checks.append(name)
    pg.sql('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role; CREATE SCHEMA extensions; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon,authenticated,service_role;')
    # Real legacy schemas/data ensure the new script cannot alter Active43.
    pg.sql((ROOT/'scripts/active43_bitget_schema.sql').read_text())
    before=pg.sql("SELECT md5(coalesce(string_agg(pg_get_functiondef(oid),'' ORDER BY proname),'')) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname LIKE 'aura_active43_bitget_%';")
    pg.sql("CREATE TABLE public.manual_verification_sentinel(value text); INSERT INTO public.manual_verification_sentinel VALUES('unchanged');")
    schema=(ROOT/'scripts/manual_paper_schema.sql').read_text()
    pg.sql(schema);pg.sql(schema)
    assert before==pg.sql("SELECT md5(coalesce(string_agg(pg_get_functiondef(oid),'' ORDER BY proname),'')) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname LIKE 'aura_active43_bitget_%';")
    assert pg.sql('SELECT value FROM public.manual_verification_sentinel;')=='unchanged'
    passed('additive_reapply_active43_unchanged')
    for role in ('anon','authenticated'):
        for sql in ['SELECT public.aura_manual_paper_v1_load(NULL);',
                    "SELECT public.aura_manual_paper_v1_lookup('"+'a'*32+"','"+'b'*64+"');",
                    'SELECT * FROM public.aura_manual_paper_v1_account;',
                    "INSERT INTO public.aura_manual_paper_v1_requests VALUES('"+'a'*32+"','"+'b'*64+"','{}',clock_timestamp());"]:
            assert pg.sql(sql,role,check=False).returncode!=0
    assert pg.sql("SELECT count(*) FROM pg_class WHERE oid IN ('public.aura_manual_paper_v1_account'::regclass,'public.aura_manual_paper_v1_requests'::regclass) AND relrowsecurity;")=='2'
    assert pg.sql("SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname LIKE 'aura_manual_paper_v1_%' AND prosecdef;")=='0'
    passed('rls_acl_invoker_no_public_execution')
    s=SQLStore(pg)
    assert s.load()==(None,0)
    s.save(ManualPaper(),0)
    assert s.load()[1]==1 and s.load()[0].balance==Decimal('10000')
    cmd=ManualCommands(s)
    opened=cmd.open('a'*32,'LONG','0.01','79500','81000',quote())
    assert Decimal(opened['balance'])==Decimal('9999.52')
    pg.restart()
    restored=SQLStore(pg);assert restored.load()[0].position.id=='a'*32
    assert ManualCommands(restored).open('a'*32,'LONG','0.010','79500','81000',quote('82000'))==opened
    closed=ManualCommands(restored).close('b'*32,quote('81000'),'a'*32)
    assert Decimal(closed['balance'])==Decimal('10009.034')
    assert ManualCommands(restored).close('b'*32,quote('99999'),'a'*32)==closed
    passed('long_restart_fees_exactly_once')
    opened=ManualCommands(restored).open('c'*32,'SHORT','0.01','80500','79000',quote())
    closed=ManualCommands(restored).close('d'*32,quote('79000'),'c'*32)
    assert Decimal(closed['result']['net'])==Decimal('9.046')
    passed('short_fees_and_permanent_history')
    for sql in ['DELETE FROM public.aura_manual_paper_v1_requests;',"UPDATE public.aura_manual_paper_v1_requests SET receipt='{}';"]:
        assert pg.sql(sql,'service_role',check=False).returncode!=0
    assert pg.sql('DELETE FROM public.aura_manual_paper_v1_requests;',check=False).returncode!=0
    passed('permanent_receipts_immutable')
    before_version=restored.load()[1]
    try:ManualCommands(restored).open('e'*32,'LONG','0.01','79500','81000',dict(quote(),time=int(time.time()*1000)-6000))
    except ValueError as e:assert str(e)=='STALE_QUOTE'
    else:raise AssertionError('stale quote accepted')
    assert restored.load()[1]==before_version
    passed('database_clock_stale_quote_rollback')
    # Force a quote that was fresh at send time to expire waiting on the SQL lock.
    from app.manual_paper.store import ManualStore
    ledger,version=SQLStore(pg).load()
    ledger.open('LONG','80000','79500','81000','0.01',candle_time=int(time.time()*1000),position_id='7'*32)
    payload=ManualStore.encode(ledger)
    args=dict(expected_version=version,new_payload=payload,new_sha256=hashlib.sha256(payload.encode()).hexdigest(),
              request_id='7'*32,intent_hash='8'*64,new_receipt=dict(request_id='7'*32,command='OPEN',
              version=version+1,balance=str(ledger.balance),result={}),quote_ms=None)
    with ThreadPoolExecutor(max_workers=1) as pool:
        blocker=pool.submit(pg.sql,'BEGIN; SELECT pg_advisory_xact_lock(77194357,1); SELECT pg_sleep(2.5); COMMIT;')
        for _ in range(50):
            if pg.sql("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid=77194357 AND objid=1 AND granted;")=='1':break
            time.sleep(.01)
        else:raise AssertionError('test lock not acquired')
        args['quote_ms']=int(time.time()*1000)-4300
        try:pg.rpc('commit',args)
        except ValueError as error:assert str(error)=='STALE_QUOTE'
        else:raise AssertionError('quote expired under lock was accepted')
        blocker.result()
    assert SQLStore(pg).load()[1]==version
    passed('quote_expiring_inside_database_lock_rollback')
    def entry(i):
        try:return ManualCommands(SQLStore(pg)).open(format(i,'032x'),'LONG','0.01','79500','81000',quote())
        except ValueError as e:return str(e)
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(entry,range(10,18)))
    assert sum(isinstance(r,dict) for r in results)==1
    passed('concurrent_process_stores_one_position')
    p=SQLStore(pg).load()[0].position
    ManualCommands(SQLStore(pg)).close('f'*32,quote(),p.id)
    def same(_):return ManualCommands(SQLStore(pg)).open('9'*32,'SHORT','0.01','80500','79000',quote())
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(same,range(8)))
    assert all(r==results[0] for r in results)
    passed('concurrent_duplicate_one_receipt')
    pg.restart()
    final,_=SQLStore(pg).load()
    assert final.position.id=='9'*32 and len(final.trades)==3
    # A migration reapply must preserve an actual populated account and receipts.
    before=pg.sql('SELECT payload FROM public.aura_manual_paper_v1_account;')
    pg.sql(schema)
    assert before==pg.sql('SELECT payload FROM public.aura_manual_paper_v1_account;')
    passed('populated_schema_reapply_restart_no_reset')
    return dict(checks=checks,POSTGRESQL_VERIFIED=True,RLS_VERIFIED=True,production_writes=False,
                real_orders=False,adapter='real_psql_rpc_not_live_PostgREST')


def run():
    if os.getenv('RENDER'):raise ValueError('LOCAL_DISPOSABLE_ONLY')
    name='aura-manual-pg-'+uuid.uuid4().hex[:12]
    docker('info','--format','{{.ServerVersion}}')
    docker('run','-d','--name',name,'--label','aura.manual.verification=true','--network','none',
           '--memory','512m','--cpus','1','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB='+DATABASE,IMAGE,timeout=180)
    try:
        wait(name);return verify(PG(name))
    finally:docker('rm','-fv',name,check=False)


if __name__=='__main__':print(json.dumps(run()))
