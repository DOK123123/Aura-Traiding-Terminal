"""Reproduce blind comparisons without inventing production Cloudflare values."""
from copy import deepcopy
import json
from pathlib import Path
import httpx
import pytest
from scripts import deploy_active43_production as d
from scripts.active43_worker_evidence import differences,equivalent
from tests.test_active43_production_deploy import Fake,release,V1,V2,NEW


@pytest.mark.parametrize('field,before,after',[
    ('compatibility_date','2026-10-20','2026-10-21'),
    ('compatibility_flags',[],['DUMMY_FLAG']),
    ('limits',{'cpu_ms':10},{'cpu_ms':11}),
    ('usage_model','standard','bundled'),
    ('observability',{'enabled':True},{'enabled':False}),
    ('annotations',{'workers/commit_sha':'a'*40},{'workers/commit_sha':'b'*40}),
])
def test_exact_setting_paths_logged_but_values_never_exposed(tmp_path,field,before,after):
    f,r,s=release(tmp_path);f.settings[field]=deepcopy(before);baseline=r.worker_state()
    f.settings[field]=deepcopy(after)
    with pytest.raises(d.Blocked,match='WORKER_SETTINGS_CHANGED'):r.invariant(baseline)
    item=r.report['comparison_failures'][-1]
    assert item['component']=='settings' and item['values_redacted']
    assert any(c['path'].startswith('$.'+field) for c in item['changes'])
    assert 'DUMMY_FLAG' not in json.dumps(item)
    assert 'a'*40 not in json.dumps(item) and 'b'*40 not in json.dumps(item)
    assert not any(x[1]=='POST' for x in f.calls)


@pytest.mark.parametrize('change',[
    lambda b:b.pop(2),
    lambda b:b[2].update(name='DUMMY_SECRET_RENAMED'),
    lambda b:b[2].update(type='plain_text',text='DUMMY_SECRET_CONTENT'),
    lambda b:b[3].update(namespace_id='DUMMY_RESOURCE_CHANGED'),
])
def test_real_binding_secret_inventory_or_type_changes_still_block(tmp_path,change):
    f,r,s=release(tmp_path);base=r.worker_state();change(f.settings['bindings'])
    with pytest.raises(d.Blocked,match='WORKER_SETTINGS_CHANGED'):r.invariant(base)
    raw=json.dumps(r.report['comparison_failures'])
    for private in ('DUMMY_SECRET_RENAMED','DUMMY_SECRET_CONTENT','DUMMY_RESOURCE_CHANGED','AURA_ACTIVE43_BITGET_SCHEDULER_SECRET'):
        assert private not in raw


def test_reordered_bindings_keep_existing_name_based_normalization(tmp_path):
    f,r,s=release(tmp_path);base=r.worker_state();f.settings['bindings'].reverse()
    r.invariant(base)
    assert not r.report.get('comparison_failures')


def test_flags_reorder_and_unknown_fields_are_not_silently_ignored(tmp_path):
    f,r,s=release(tmp_path);f.settings['compatibility_flags']=['DUMMY_ONE','DUMMY_TWO'];base=r.worker_state()
    f.settings['compatibility_flags'].reverse()
    with pytest.raises(d.Blocked):r.invariant(base)
    assert differences({'DUMMY_PRIVATE_FIELD':'DUMMY_PRIVATE_VALUE'},{'DUMMY_PRIVATE_FIELD':'changed'})['changes'][0]['path']=='$.unknown_field_0'
    assert 'DUMMY_PRIVATE' not in json.dumps(differences({'DUMMY_PRIVATE_FIELD':'DUMMY_PRIVATE_VALUE'},{}))


def test_json_bool_is_not_number_and_numeric_encoding_is_equivalent():
    assert not equivalent({'enabled':True},{'enabled':1})
    assert differences({'enabled':True},{'enabled':1})['changes'][0]==dict(path='$.enabled',before_type='boolean',after_type='number',change='different')
    assert equivalent({'cpu_ms':10},{'cpu_ms':10.0})
    assert not equivalent(float('nan'),float('nan'))


def test_cron_and_subdomain_changes_remain_guarded(tmp_path):
    for path,body,expected in [('/schedules',{'schedules':[{'cron':'DUMMY_CHANGED_CRON'}]},'$.schedules[0].cron'),
                              ('/subdomain',{'enabled':True,'previews_enabled':False},'$.enabled')]:
        f,r,s=release(tmp_path);base=r.worker_state();original=f.call
        def changed(realm,method,p='',data=None,files=None):
            return deepcopy(body) if realm=='cf' and p==path else original(realm,method,p,data,files)
        f.call=changed
        with pytest.raises(d.Blocked,match='WORKER_ROUTING_OR_CRON_CHANGED'):r.invariant(base)
        assert expected in [c['path'] for c in r.report['comparison_failures'][-1]['changes']]
        assert 'DUMMY_CHANGED' not in json.dumps(r.report)


def test_post_upload_settings_failure_records_field_and_never_activates(tmp_path):
    f,r,s=release(tmp_path);original=f.call
    def changed(realm,method,path='',data=None,files=None):
        value=original(realm,method,path,data,files)
        if realm=='cf' and method=='POST' and path.startswith('/versions?'):
            f.settings['observability']={'enabled':False}
        return value
    f.call=changed
    with pytest.raises(d.Blocked,match='WORKER_SETTINGS_CHANGED'):r.deploy(17,s)
    assert r.report['staged_worker_version_id']==V2 and f.active==V1
    assert r.report['comparison_failures'][-1]['changes'][0]['path']=='$.observability'
    assert not any(x[0:3]==('cf','POST','/deployments') for x in f.calls)


def test_existing_staged_rerun_collects_evidence_and_does_no_posts(tmp_path):
    f,r,s=release(tmp_path);f.latest=V2
    with pytest.raises(d.Blocked,match='UNDEPLOYED_WORKER_VERSION_REQUIRES_REVIEW'):r.deploy(17,s)
    evidence=r.report['worker_diagnostics']
    assert evidence['active_version_id']==V1 and evidence['inspected_version_id']==V2
    assert evidence['root_cause_confirmed'] is False and evidence['safe_to_resume'] is False
    assert evidence['missing_evidence']=='FAILED_RUN_PRE_UPLOAD_SETTINGS_SNAPSHOT_NOT_CAPTURED'
    assert not any(x[1]=='POST' for x in f.calls)


def test_read_only_inspection_exposes_protected_resource_paths_not_values(tmp_path):
    f,r,s=release(tmp_path);f.latest=V2;f.staged_drift=True
    result=r.inspect_worker()
    assert result['active_staged_resources']['script_runtime']['changes'][0]['path']=='$.compatibility_date'
    assert not result['active_staged_resources']['script_runtime']['equal']
    assert result['read_only'] and not result['secret_value_equality_verified']
    assert '2000-01-01' not in json.dumps(result)
    assert not any(x[1]!='GET' for x in f.calls)


def test_remote_read_only_mode_rejects_even_approved_mutator_paths_before_network():
    env=dict(AURA_RENDER_SERVICE_ID='srv-'+'a'*20,AURA_CLOUDFLARE_ACCOUNT_ID='b'*32,
        AURA_RENDER_API_KEY='DUMMY_RENDER_KEY',AURA_CLOUDFLARE_API_TOKEN='DUMMY_CF_TOKEN',
        AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_PASSWORD',GITHUB_TOKEN='DUMMY_GITHUB_TOKEN')
    remote=d.Remote(env,read_only=True)
    try:
        for realm,path in [('render','/deploys'),('cf','/deployments'),('cf','/versions?bindings_inherit=strict')]:
            with pytest.raises(d.Blocked,match='READ_ONLY_INSPECTION_WRITE_FORBIDDEN'):remote.call(realm,'POST',path)
    finally:remote.close()


def test_bounded_diagnostics_do_not_print_unknown_keys_values_or_lengths():
    before={f'DUMMY_PRIVATE_KEY_{i}':f'DUMMY_PRIVATE_VALUE_{i}' for i in range(100)}
    result=differences(before,{},limit=4)
    assert len(result['changes'])==4 and result['truncated']
    assert 'DUMMY_PRIVATE' not in json.dumps(result)
    assert all(set(row)=={'path','before_type','after_type','change'} for row in result['changes'])


def test_inspection_workflow_exists_does_not_require_cron_or_paper_changes():
    workflow=json.loads(Path('.github/workflows/production-deploy.yml').read_text())
    assert 'inspect_worker' in workflow['on']['workflow_dispatch']['inputs']['operation']['options']
    expression=workflow['jobs']['production']['if']
    assert "inputs.operation == 'inspect_worker'" in expression and "github.ref == 'refs/heads/main'" in expression
    step=next(s for s in workflow['jobs']['production']['steps'] if 'RELEASE_OPERATION' in s.get('env',{}))
    assert '--inspect-version "$INSPECT_WORKER_VERSION"' in step['run']


def test_inspection_dispatch_is_allowed_when_deploy_disabled_but_never_on_other_branch():
    import ast
    workflow=json.loads(Path('.github/workflows/production-deploy.yml').read_text())
    expression=workflow['jobs']['production']['if']
    def allowed(operation,ref='refs/heads/main'):
        fields={'github.ref':ref,'vars.AURA_PRODUCTION_DEPLOY_ENABLED':'false',
            'github.event_name':'workflow_dispatch','inputs.operation':operation,
            'github.event.workflow_run.conclusion':'success','github.event.workflow_run.event':'push',
            'github.event.workflow_run.head_branch':'main','github.event.workflow_run.head_repository.full_name':d.REPO,
            'github.repository':d.REPO}
        value=expression
        for key in sorted(fields,key=len,reverse=True):value=value.replace(key,repr(fields[key]))
        tree=ast.parse(value.replace('&&',' and ').replace('||',' or '),mode='eval')
        assert all(isinstance(n,(ast.Expression,ast.BoolOp,ast.And,ast.Or,ast.Compare,ast.Eq,ast.Constant,ast.Load)) for n in ast.walk(tree))
        return eval(compile(tree,'actual-inspect-condition','eval'),{'__builtins__':{}},{})
    assert allowed('inspect_worker')
    assert not allowed('deploy') and not allowed('rollback')
    assert not allowed('inspect_worker','refs/heads/other')


def test_inspection_cli_cannot_activate_even_with_deploy_enabled_false(tmp_path,monkeypatch):
    f,r,source=release(tmp_path);f.latest=V2
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('AURA_PRODUCTION_DEPLOY_ENABLED','false')
    monkeypatch.setattr('sys.argv',['release','--operation','inspect_worker','--sha',NEW,'--ci-run-id','17'])
    def remote(env,read_only=False):
        assert read_only is True
        return f
    f.close=lambda:None
    monkeypatch.setattr(d,'Remote',remote)
    assert d.main()==0
    report=json.loads(Path('release-results/deployment-report.json').read_text())
    assert report['status']=='WORKER_INSPECTED_NO_DEPLOYMENT' and report['mutations']==[]
    assert not report['worker_diagnostics']['safe_to_resume']
    assert all(method=='GET' for _,method,_,_ in f.calls)


@pytest.mark.parametrize('before,after',[(None,[]),({},None),('2026-10-20','2026-10-20T00:00:00Z'),([],['DUMMY_FLAG'])])
def test_shape_dates_and_defaults_not_guessed_equivalent(before,after):
    assert not equivalent({'compatibility_date':before},{'compatibility_date':after})
    result=differences({'compatibility_date':before},{'compatibility_date':after})
    assert result['changes'] and result['values_redacted']
    assert '2026-' not in json.dumps(result) and 'DUMMY_FLAG' not in json.dumps(result)
