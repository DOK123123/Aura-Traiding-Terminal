"""Disposable PostgreSQL signal storage/outbox test. Never sends a notification/order."""
import base64,json,time,uuid
from pathlib import Path
from scripts.verify_manual_paper_postgres import PG,wait,DATABASE
from scripts.verify_practice_postgres import docker,IMAGE
from scripts.build_manual_preview_sql import rendered
from app.manual_preview.lifecycle import reduce_signal

REF='kkxdftdojvnsjqlrulpb'

def verify(pg):
    pg.sql('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;')
    pg.sql(rendered(REF))
    sql=Path('scripts/sql/aura5_signal_lock.sql').read_text();pg.sql(sql);pg.sql(sql)
    def rpc(action,data=None,role='service_role'):
        raw=base64.b64encode(json.dumps(data or {}).encode()).decode()
        result=pg.sql("SET request.jwt.claims = '{\"role\":\"service_role\"}'; SELECT public.aura5_signals_rpc('"+action+"',convert_from(decode('"+raw+"','base64'),'UTF8')::jsonb);",role=role)
        return json.loads(result) if result else None
    for role in ('anon','authenticated'):
        assert pg.sql("SELECT public.aura5_signals_rpc('load');",role=role,check=False).returncode!=0
    assert rpc('load')=={'version':0,'records':[]}
    sid='d'*64
    rpc('subscribe',{'id':sid,'subscription':{'endpoint':'DUMMY_ONLY_NOT_NETWORK'},'candidate':False})
    now=time.time()
    c=dict(strategy='TREND_PULLBACK',direction='LONG',frame='15m',structure={'pivot_time':900},score=75,
           checks=[{'code':'TREND','passed':False}],rejection=['TREND'],valid_until=now+1000,entry=100,sl=95,tp=110,net_rr=1.7)
    row,event=reduce_signal(None,c,now,trusted=True);row['refreshed_at']=now
    assert rpc('commit',{'version':0,'records':[row],'events':[event]})['version']==1
    assert rpc('claim') is None # WATCH-only subscription ignores CANDIDATE
    c['checks'][0]['passed']=True;c['rejection']=[]
    row,event=reduce_signal(row,c,now+.1,trusted=True);row['refreshed_at']=now
    rpc('commit',{'version':1,'records':[row],'events':[event]})
    assert rpc('commit',{'version':1,'records':[row],'events':[event]})['conflict']
    rpc('commit',{'version':2,'records':[row],'events':[event]}) # replay doesn't create another outbox item
    pg.restart()
    assert rpc('load')['records'][0]['id']==row['id']
    # Refresh only metadata after test database restart; retain actual event identity.
    row['refreshed_at']=time.time()
    rpc('commit',{'version':3,'records':[row],'events':[]})
    job=rpc('claim');assert job['kind']=='WATCH'
    assert rpc('claim') is None
    rpc('finish',{'id':job['id'],'state':'ACCEPTED_BY_PUSH_SERVICE','code':201})
    delivery=rpc('delivery',{'id':sid});assert delivery[0]['state']=='ACCEPTED_BY_PUSH_SERVICE'
    assert pg.sql('SELECT count(*) FROM aura5_signals.events;')=='2'
    assert pg.sql('SELECT count(*) FROM aura5_signals.outbox;')=='1'
    # Schema never changes wallet tables or the public isolation allowlist.
    assert rpc('load')['version']==4
    assert json.loads(pg.sql("SET request.jwt.claims = '{\"role\":\"service_role\"}'; SELECT public.aura_manual_preview_guard();",role='service_role'))['isolated']
    return {'status':'PASS','checks':['RLS_AND_ROLE_DENIAL','CAS_CONFLICT','CANDIDATE_WATCH','EVENT_OUTBOX_DEDUP','DATABASE_RESTART','CLAIM_ONCE','PROVIDER_ACCEPTED_NOT_DELIVERED','WALLET_SCOPE_UNCHANGED']}

def run():
    name='aura-manual-pg-'+uuid.uuid4().hex[:12]
    docker('run','-d','--name',name,'--label','aura.manual.verification=true','--network','none','--memory','512m','--cpus','1','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB='+DATABASE,IMAGE)
    try:wait(name);return verify(PG(name))
    finally:docker('rm','-fv',name,check=False)
if __name__=='__main__':print(json.dumps(run()))
