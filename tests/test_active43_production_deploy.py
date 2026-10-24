"""No production credentials or network: deterministic release API model."""
from copy import deepcopy
import json
from pathlib import Path
import re
import httpx
import pytest
from scripts import deploy_active43_production as d

NEW='b'*40;OLD='a'*40
V1='11111111-1111-1111-1111-111111111111';V2='22222222-2222-2222-2222-222222222222'


class Fake:
    def __init__(self):
        self.now=1800000150;self.current=OLD;self.active=V1;self.latest=V1;self.calls=[];self.changed_ledger=False
        self.settings=dict(compatibility_date='2026-10-20',compatibility_flags=[],bindings=[
            dict(name='AURA_ACTIVE43_OPERATION',type='plain_text',text='saved_mode'),
            dict(name='AURA_ACTIVE43_CRON_ENABLED',type='plain_text',text='true'),
            dict(name='AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',type='secret_text'),
            dict(name='EXISTING_KV',type='kv_namespace',namespace_id='DUMMY_EXISTING_ONLY')])
        self.resources=dict(bindings=deepcopy(self.settings['bindings']),script_runtime={k:self.settings[k] for k in ('compatibility_date','compatibility_flags')})
        self.fail=None;self.ci='success';self.evidence=True;self.staged_drift=False;self.manual_tick=False
    def sleep(self,n):self.now+=n
    def call(self,realm,method,path='',data=None,files=None):
        self.calls.append((realm,method,path,deepcopy(data)))
        if self.fail==(realm,method,path):raise d.Blocked('SIMULATED_FAILURE')
        if realm=='github':
            if path=='/commits/main':return {'sha':NEW}
            if path.startswith('/compare/'):return dict(status='ahead',merge_base_commit={'sha':OLD})
            if path=='/actions/workflows/regression.yml':return {'id':42}
            if path=='/actions/runs/17':return dict(head_sha=NEW,head_branch='main',event='push',head_repository={'full_name':d.REPO},workflow_id=42,status='completed',conclusion=self.ci)
            if path.endswith('/jobs?filter=latest&per_page=100'):return dict(total_count=1,jobs=[dict(name=d.CI_JOB,conclusion=self.ci,steps=[dict(name=n,conclusion=self.ci) for n in ('Run actual regressions with no external network and no production secrets','Upload actual test reports')])])
        if realm=='aura':
            assert method=='GET'
            if path=='/api/health':return {'status':'ok'}
            if path=='/api/active43/paper-readiness':return dict(status='READY',scope='AURA43_ACTIVE_PAPER',read_only=True,state_changed=False,paper_only=True,exchange_execution=False,errors=[],account={'mode':'OFF'},market={'status':'PASS','history_complete':True,'last_closed_at':self.now//300*300})
            if path=='/api/active43/deployment-readiness':
                at=self.now//300*300+120
                if at>self.now:at-=300
                ticks=[dict(tick_id='ACTIVE43_BITGET_'+'f'*32+':tick:'+str((at-i*300)//300),
                    scheduled_at=at-i*300,created_at=at-i*300+5,render_commit=self.current,
                    invocation_id=str(i+1)*32,status='COMPLETED',state_saved=True,mode='OFF',opened=0,closed=0) for i in (0,1)]
                return dict(scope='AURA43_ACTIVE_PAPER',read_only=True,state_changed=False,paper_only=True,exchange_execution=False,status='PASS',errors=[],checked_at=self.now,render_commit=self.current,
                    account=dict(mode='OFF',balance='10000',open_positions=0,pending_operations=0,risk_code=None,ledger_sha256=('e' if self.changed_ledger else 'd')*64),
                    scheduler=dict(status='PASS' if self.evidence and not self.manual_tick else 'BLOCKED',ticks=ticks if self.evidence else []))
        if realm=='render':
            if path=='':return dict(type='web_service',branch='main',repo='https://github.com/'+d.REPO,serviceDetails={'url':d.ORIGIN},autoDeployTrigger='off')
            if method=='POST':
                assert path=='/deploys';self.requested=data['commitId'];return {'id':'dep-'+'x'*16}
            if path.startswith('/deploys?'):return [dict(deploy=dict(status='live',commit={'id':self.current})),dict(deploy=dict(status='deactivated',commit={'id':OLD}))]
            if path.startswith('/deploys/'):self.current=self.requested;return dict(status='live',commit={'id':self.current})
        if realm=='cf':
            if path=='/settings':return deepcopy(self.settings)
            if path=='/schedules':return {'schedules':[{'cron':d.CRON}]}
            if path=='/routes':return []
            if path=='/subdomain':return dict(enabled=False,previews_enabled=False)
            if method=='POST' and path=='/versions?bindings_inherit=strict':
                metadata=json.loads(files['metadata'][1]);self.metadata=metadata;self.upload=files['worker.mjs'][1]
                assert all(b['type']=='inherit' for b in metadata['bindings'])
                self.latest=V2;return {'id':V2}
            if path.startswith('/versions?'):return dict(items=[dict(id=self.latest,number=2)])
            if path.startswith('/versions/'):
                resources=deepcopy(self.resources)
                if self.staged_drift and path.endswith(V2):resources['script_runtime']['compatibility_date']='2000-01-01'
                return dict(id=path.rsplit('/',1)[-1],resources=resources)
            if method=='POST' and path=='/deployments':self.active=data['versions'][0]['version_id'];return {'id':'DUMMY_DEPLOYMENT'}
            if path=='/deployments':return dict(deployments=[dict(created_on='2026-10-24T00:00:00Z',versions=[dict(version_id=self.active,percentage=100)])])
        raise AssertionError((realm,method,path))


def release(tmp_path,f=None):
    f=f or Fake();r=d.Release(f,NEW,tmp_path/'report.json',clock=lambda:f.now,sleep=f.sleep)
    source=tmp_path/'worker.mjs';source.write_text('export default {async scheduled(){},fetch(){return new Response("test")}}')
    return f,r,source


def test_complete_order_ci_render_exact_sha_worker_existing_preserved_receipts(tmp_path):
    f,r,source=release(tmp_path);before=deepcopy(f.settings);r.deploy(17,source)
    assert r.report['status']=='DEPLOY_VERIFIED' and r.report['previous_render_commit']==OLD
    assert r.report['previous_worker_version_id']==V1 and r.report['worker_version_id']==V2
    assert len(r.report['automatic_ticks'])==2 and not r.report['production_paper_verified']
    writes=[x for x in f.calls if x[1]=='POST'];assert [x[:3] for x in writes]==[
        ('render','POST','/deploys'),('cf','POST','/versions?bindings_inherit=strict'),('cf','POST','/deployments')]
    upload_at=next(i for i,x in enumerate(f.calls) if x[0:3]==writes[1][0:3])
    assert ('aura','GET','/api/health',None) in f.calls[:upload_at]
    assert f.settings==before and f.upload==source.read_bytes()
    assert {b['name'] for b in f.metadata['bindings']}=={b['name'] for b in before['bindings']}
    assert not any('/tick' in x[2] or '/control' in x[2] or '/initialize' in x[2] for x in f.calls)


@pytest.mark.parametrize('ci',['skipped','failure',None])
def test_ci_not_success_never_writes(tmp_path,ci):
    f,r,s=release(tmp_path);f.ci=ci
    with pytest.raises(d.Blocked):r.deploy(17,s)
    assert not any(x[1]=='POST' for x in f.calls)


@pytest.mark.parametrize('fault',[('aura','GET','/api/active43/deployment-readiness'),('render','POST','/deploys')])
def test_failed_account_or_render_never_uploads_worker(tmp_path,fault):
    f,r,s=release(tmp_path);f.fail=fault
    with pytest.raises(d.Blocked):r.deploy(17,s)
    assert not any(x[0]=='cf' and x[1]=='POST' for x in f.calls)


def test_staged_runtime_drift_never_activates(tmp_path):
    f,r,s=release(tmp_path);f.staged_drift=True
    with pytest.raises(d.Blocked,match='STAGED_WORKER_CONFIG_CHANGED'):r.deploy(17,s)
    assert f.active==V1 and f.latest==V2


def test_ledger_drift_never_uploads_or_changes_mode(tmp_path):
    f,r,s=release(tmp_path);r.off(OLD);f.changed_ledger=True
    with pytest.raises(d.Blocked,match='FINANCIAL_LEDGER_CHANGED'):r.deploy(17,s)
    assert not any(x[1]=='POST' for x in f.calls)


@pytest.mark.parametrize('manual',[False,True])
def test_http_200_is_not_persistence_or_automatic_proof(tmp_path,manual):
    f,r,s=release(tmp_path);f.evidence=manual;f.manual_tick=manual
    with pytest.raises(d.Blocked,match='TWO_POST_DEPLOY_AUTOMATIC_TICKS_NOT_CONFIRMED'):r.deploy(17,s)
    assert r.report['automatic_ticks']==[]


def test_existing_worker_only_and_settings_never_rewritten():
    text=Path('scripts/deploy_active43_production.py').read_text()
    assert d.WORKER=='aura-ctive43-scheduler'
    assert 'wrangler' not in text
    assert not re.search(r"call\('cf','(?:PUT|PATCH|DELETE)'",text)
    settings=Fake().settings;before=deepcopy(settings);m=d.upload_metadata(settings,NEW)
    assert settings==before and 'vars' not in m and 'triggers' not in m
    assert all(b==dict(name=b['name'],type='inherit') for b in m['bindings'])


def test_rollback_worker_before_render_and_financial_state_unchanged(tmp_path):
    f,r,s=release(tmp_path);f.current=NEW;f.active=V2;f.latest=V2
    r.rollback(OLD,V1,'ROLLBACK PAPER OFF NO CONFIG ROTATION')
    assert r.report['status']=='ROLLBACK_VERIFIED'
    writes=[x for x in f.calls if x[1]=='POST']
    assert writes[0][0:3]==('cf','POST','/deployments') and writes[1][0:3]==('render','POST','/deploys')
    assert f.current==OLD and f.active==V1


def test_stale_main_and_wrong_cron_block_before_deploy(tmp_path):
    f,r,s=release(tmp_path)
    with pytest.raises(d.Blocked,match='STALE_MAIN_SHA'):
        r.sha=OLD;r.deploy(17,s)
    assert not any(x[1]=='POST' for x in f.calls)


def test_workflow_disabled_default_exact_ci_trusted_main_no_parallel_or_secret_shell_interpolation():
    text=Path('.github/workflows/production-deploy.yml').read_text();value=json.loads(text)
    assert value['concurrency']==dict(group='aura43-production',**{'cancel-in-progress':False})
    job=value['jobs']['production'];assert "vars.AURA_PRODUCTION_DEPLOY_ENABLED == 'true'" in job['if']
    assert "github.event.workflow_run.event == 'push'" in job['if']
    assert job['environment']=='production'
    for step in job['steps']:
        if 'uses' in step:assert re.search('@[a-f0-9]{40}$',step['uses'])
        assert '${{ secrets.' not in step.get('run','') and '${{ inputs.' not in step.get('run','')
    assert 'wrangler' not in text and 'curl' not in text


def test_remote_forbidden_mutations_and_no_secret_error_leak(monkeypatch):
    env=dict(AURA_RENDER_SERVICE_ID='srv-'+'a'*20,AURA_CLOUDFLARE_ACCOUNT_ID='b'*32,
        AURA_RENDER_API_KEY='DUMMY_RENDER_KEY',AURA_CLOUDFLARE_API_TOKEN='DUMMY_CF_TOKEN',
        AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_PASSWORD',GITHUB_TOKEN='DUMMY_GITHUB_TOKEN')
    r=d.Remote(env)
    try:
        with pytest.raises(d.Blocked,match='API_WRITE_FORBIDDEN'):r.call('aura','POST','/api/active43/tick')
        with pytest.raises(d.Blocked,match='API_WRITE_FORBIDDEN'):r.call('cf','POST','/settings',{})
        def broken(req):raise httpx.ReadTimeout('DUMMY_PRIVATE_VALUE')
        r.client.close();r.client=httpx.Client(transport=httpx.MockTransport(broken))
        with pytest.raises(d.Blocked,match='RENDER_WRITE_OUTCOME_UNKNOWN') as err:r.call('render','POST','/deploys',{})
        assert 'DUMMY_PRIVATE' not in str(err.value)
    finally:r.close()


def test_actual_workflow_event_expression_blocks_pr_failure_disabled_and_foreign_repo():
    import ast
    job=json.loads(Path('.github/workflows/production-deploy.yml').read_text())['jobs']['production']
    expression=job['if']
    def allowed(**overrides):
        fields={'github.ref':'refs/heads/main','vars.AURA_PRODUCTION_DEPLOY_ENABLED':'true','github.event_name':'workflow_run',
            'github.event.workflow_run.conclusion':'success','github.event.workflow_run.event':'push',
            'github.event.workflow_run.head_branch':'main','github.event.workflow_run.head_repository.full_name':d.REPO,
            'github.repository':d.REPO}
        fields.update(overrides);value=expression
        for key in sorted(fields,key=len,reverse=True):value=value.replace(key,repr(fields[key]))
        value=value.replace('&&',' and ').replace('||',' or ')
        tree=ast.parse(value,mode='eval')
        assert all(isinstance(n,(ast.Expression,ast.Constant,ast.BoolOp,ast.And,ast.Or,ast.Compare,ast.Eq,ast.Load)) for n in ast.walk(tree))
        return eval(compile(tree,'actual-workflow','eval'),{'__builtins__':{}},{})
    assert allowed()
    for fields in ({'github.ref':'refs/heads/other'}, {'vars.AURA_PRODUCTION_DEPLOY_ENABLED':'false'},
        {'github.event.workflow_run.event':'pull_request'},
        {'github.event.workflow_run.head_branch':'other'},
        {'github.event.workflow_run.conclusion':'skipped'},
        {'github.event.workflow_run.head_repository.full_name':'DUMMY/foreign'}):assert not allowed(**fields)


def test_remote_get_retry_after_and_redirect_protection(monkeypatch):
    env=dict(AURA_RENDER_SERVICE_ID='srv-'+'a'*20,AURA_CLOUDFLARE_ACCOUNT_ID='b'*32,
        AURA_RENDER_API_KEY='DUMMY_RENDER_KEY',AURA_CLOUDFLARE_API_TOKEN='DUMMY_CF_TOKEN',
        AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_PASSWORD',GITHUB_TOKEN='DUMMY_GITHUB_TOKEN')
    r=d.Remote(env);calls=[];waits=[]
    def handler(req):
        calls.append(req)
        if len(calls)==1:return httpx.Response(429,headers={'Retry-After':'3'},json={})
        return httpx.Response(200,json={'status':'ok'})
    r.client.close();r.client=httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False)
    monkeypatch.setattr(d.time,'sleep',waits.append)
    assert r.call('aura','GET','/api/health')=={'status':'ok'} and waits==[3] and len(calls)==2
    r.client.close();r.client=httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(302,headers={'Location':'https://DUMMY.invalid'})))
    with pytest.raises(d.Blocked,match='AURA_HTTP_302'):r.call('aura','GET','/api/health')
    r.close()


def test_unsafe_worker_modes_and_unreleased_version_fail_before_writes(tmp_path):
    f,r,s=release(tmp_path);f.settings['bindings'][0]['text']='diagnostics'
    with pytest.raises(d.Blocked,match='WORKER_OPERATION_NOT_SAVED_MODE'):r.deploy(17,s)
    assert not any(x[1]=='POST' for x in f.calls)
    f,r,s=release(tmp_path);f.latest=V2
    with pytest.raises(d.Blocked,match='UNDEPLOYED_WORKER_VERSION_REQUIRES_REVIEW'):r.deploy(17,s)
    assert not any(x[1]=='POST' for x in f.calls)


def test_no_execute_never_uses_credentials_or_network(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path);monkeypatch.setattr('sys.argv',['release','--sha',NEW])
    monkeypatch.setattr(d,'Remote',lambda *_:pytest.fail('NO_REMOTE_WITHOUT_AUTHORIZATION'))
    assert d.main()==1
    assert json.loads(Path('release-results/deployment-report.json').read_text())['code']=='DEPLOY_NOT_AUTHORIZED'


def test_real_cron_mismatch_wrong_render_identity_and_active_splits_block(tmp_path):
    for failure in ('cron','render','split'):
        f,r,s=release(tmp_path);original=f.call
        def broken(realm,method,path='',data=None,files=None):
            value=original(realm,method,path,data,files)
            if failure=='cron' and realm=='cf' and path=='/schedules':return {'schedules':[{'cron':'* * * * *'}]}
            if failure=='render' and realm=='render' and path=='':value['serviceDetails']['url']='https://DUMMY.invalid'
            if failure=='split' and realm=='cf' and path=='/deployments':value['deployments'][0]['versions'].append({'version_id':V2,'percentage':50})
            return value
        f.call=broken
        with pytest.raises(d.Blocked):r.deploy(17,s)
        assert not any(x[1]=='POST' for x in f.calls)


def test_duplicate_tick_ids_and_wrong_origin_sha_never_verify(tmp_path):
    for failure in ('duplicate','origin'):
        f,r,s=release(tmp_path);original=f.call
        def broken(realm,method,path='',data=None,files=None):
            value=original(realm,method,path,data,files)
            if realm=='aura' and path.endswith('/deployment-readiness'):
                ticks=value['scheduler']['ticks']
                if failure=='duplicate':ticks[1]['tick_id']=ticks[0]['tick_id']
                else:ticks[0]['render_commit']=OLD
            return value
        f.call=broken
        with pytest.raises(d.Blocked,match='TWO_POST_DEPLOY_AUTOMATIC_TICKS_NOT_CONFIRMED'):r.deploy(17,s)
        assert not r.report['automatic_ticks']


def test_existing_owner_password_is_not_trimmed_or_changed():
    env=dict(AURA_RENDER_SERVICE_ID='srv-'+'a'*20,AURA_CLOUDFLARE_ACCOUNT_ID='b'*32,
        AURA_RENDER_API_KEY='DUMMY_RENDER_KEY',AURA_CLOUDFLARE_API_TOKEN='DUMMY_CF_TOKEN',
        AURA_TESTNET_VIEW_PASSWORD=' DUMMY_ПАРОЛЬ ',GITHUB_TOKEN='DUMMY_GITHUB_TOKEN')
    r=d.Remote(env)
    import base64
    decoded=base64.b64decode(r.headers['aura']['Authorization'].split(' ',1)[1]).decode()
    assert decoded=='aura:'+env['AURA_TESTNET_VIEW_PASSWORD'];r.close()


def test_embedded_workflow_shell_is_valid_without_executing_it():
    import subprocess
    value=json.loads(Path('.github/workflows/production-deploy.yml').read_text())
    for step in value['jobs']['production']['steps']:
        if 'run' in step:subprocess.run(['bash','-n'],input=step['run'],text=True,check=True,capture_output=True)
