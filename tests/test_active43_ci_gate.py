"""Actual Issue36 metadata, no provider requests or production credentials."""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
import pytest
from scripts import deploy_active43_production as d
from tests.test_active43_production_deploy import Fake,release,NEW

FIXTURE=json.loads(Path('tests/fixtures/active43_issue36_ci.json').read_text())


class RecordedGithub(Fake):
    def call(self,realm,method,path='',data=None,files=None):
        assert realm=='github' and method=='GET' and data is None and files is None
        self.calls.append((realm,method,path,None))
        if path=='/commits/main':return {'sha':FIXTURE['main_sha']}
        if path=='/actions/workflows/regression.yml':return deepcopy(FIXTURE['workflow'])
        for key in ('submitted_ci_run_id','trusted_ci_run_id'):
            id=FIXTURE[key]
            if path=='/actions/runs/'+str(id):return deepcopy(FIXTURE['runs'][str(id)])
            if path=='/actions/runs/'+str(id)+'/jobs?filter=latest&per_page=100':return deepcopy(FIXTURE['jobs'])
        if path.startswith('/actions/workflows/'+str(FIXTURE['workflow']['id'])+'/runs?'):
            query=parse_qs(urlsplit(path).query)
            assert query['head_sha']==[FIXTURE['main_sha']] and query['event']==['push'] and query['branch']==['main']
            return dict(total_count=1,workflow_runs=[deepcopy(FIXTURE['runs'][str(FIXTURE['trusted_ci_run_id'])])])
        if path=='/environments/production':return dict(deployment_branch_policy={'custom_branch_policies':True,'protected_branches':False})
        if path.startswith('/environments/production/deployment-branch-policies'):return dict(total_count=1,branch_policies=[dict(name='main',type='branch')])
        raise AssertionError(path)


def test_issue36_reproduction_proves_wrong_submitted_id_not_false_success_rejection(tmp_path):
    remote=RecordedGithub();r=d.Release(remote,FIXTURE['main_sha'],tmp_path/'report.json')
    with pytest.raises(d.Blocked,match='EXACT_MAIN_CI_NOT_SUCCESSFUL'):r.verify_ci(FIXTURE['submitted_ci_run_id'])
    proof=r.report['ci_validation']
    assert proof['failed_checks']==['run_head_sha']
    assert proof['actual_head_sha']=='af325769663b0d6593b64eb844e56558957e6647'
    assert proof['expected_head_sha']==FIXTURE['main_sha']
    assert proof['run_conclusion']=='success' and proof['run_status']=='completed'
    assert not any('/runs?' in path for _,_,path,_ in remote.calls)


def test_actual_correct_main_ci_passes_all_identity_job_step_and_environment_guards(tmp_path):
    r=d.Release(RecordedGithub(),FIXTURE['main_sha'],tmp_path/'report.json')
    r.verify_ci(FIXTURE['trusted_ci_run_id'])
    assert r.report['ci_validation']['status']=='PASS'
    assert all(r.report['ci_validation']['checks'].values())
    assert not r.report['mutations']


def test_empty_input_discovers_only_trusted_exact_sha_then_verifies_full_run(tmp_path):
    remote=RecordedGithub();r=d.Release(remote,FIXTURE['main_sha'],tmp_path/'report.json');r.verify_ci(0)
    assert r.report['ci_run_id']==FIXTURE['trusted_ci_run_id']
    assert r.report['ci_validation']['selection']=='EXACT_SHA_DISCOVERY'
    assert r.report['ci_validation']['status']=='PASS'
    assert all(method=='GET' and realm=='github' for realm,method,_,_ in remote.calls)


@pytest.mark.parametrize('field,value,failed',[
    ('id',999,'run_id_matches_request'),('head_sha','c'*40,'run_head_sha'),
    ('head_branch','DUMMY_PRIVATE_BRANCH','run_branch'),('event','pull_request','run_event'),
    ('workflow_id',123,'run_workflow_id'),('head_repository',{'full_name':'DUMMY_PRIVATE_REPO'},'run_repository'),
    ('head_repository',None,'run_repository'),('status','in_progress','run_completed'),
    ('conclusion','skipped','run_success'),('conclusion','failure','run_success'),
])
def test_adversarial_run_metadata_fails_closed_without_logging_unknown_values(tmp_path,field,value,failed):
    class Changed(RecordedGithub):
        def call(self,realm,method,path='',data=None,files=None):
            v=super().call(realm,method,path,data,files)
            if path=='/actions/runs/'+str(FIXTURE['trusted_ci_run_id']):v[field]=deepcopy(value)
            return v
    r=d.Release(Changed(),FIXTURE['main_sha'],tmp_path/'report.json')
    with pytest.raises(d.Blocked,match='EXACT_MAIN_CI_NOT_SUCCESSFUL'):r.verify_ci(FIXTURE['trusted_ci_run_id'])
    assert failed in r.report['ci_validation']['failed_checks']
    assert 'DUMMY_PRIVATE' not in json.dumps(r.report)


@pytest.mark.parametrize('change,expected',[
    (lambda j:j['jobs'][0].update(conclusion='skipped'),'regression_job_completed_success'),
    (lambda j:j['jobs'][0].update(status='in_progress'),'regression_job_completed_success'),
    (lambda j:j['jobs'][0].update(name='DUMMY_PRIVATE_JOB_NAME'),'regression_job_name'),
    (lambda j:j['jobs'][0]['steps'].pop(next(i for i,s in enumerate(j['jobs'][0]['steps']) if s['name']=='Upload actual test reports')),'step:Upload actual test reports'),
    (lambda j:next(s for s in j['jobs'][0]['steps'] if s['name']=='Run actual regressions with no external network and no production secrets').update(conclusion='skipped'),'step:Run actual regressions with no external network and no production secrets'),
])
def test_top_level_success_cannot_hide_skipped_job_or_missing_regression_reports(tmp_path,change,expected):
    class Changed(RecordedGithub):
        def call(self,realm,method,path='',data=None,files=None):
            v=super().call(realm,method,path,data,files)
            if '/jobs?' in path:change(v)
            return v
    r=d.Release(Changed(),FIXTURE['main_sha'],tmp_path/'report.json')
    with pytest.raises(d.Blocked):r.verify_ci(FIXTURE['trusted_ci_run_id'])
    assert expected in r.report['ci_validation']['failed_checks']
    assert r.report['ci_validation']['status']=='BLOCKED' and 'DUMMY_PRIVATE_JOB' not in json.dumps(r.report)


@pytest.mark.parametrize('bad',[
    dict(head_sha='e'*40),dict(event='pull_request'),dict(head_branch='other'),dict(conclusion='skipped'),
    dict(workflow_id=123),dict(head_repository={'full_name':'DUMMY/foreign'}),dict(status='in_progress'),
])
def test_discovery_does_not_trust_github_filter_without_rechecking_each_candidate(tmp_path,bad):
    class Changed(RecordedGithub):
        def call(self,realm,method,path='',data=None,files=None):
            v=super().call(realm,method,path,data,files)
            if '/runs?' in path:v['workflow_runs'][0].update(bad)
            return v
    r=d.Release(Changed(),FIXTURE['main_sha'],tmp_path/'report.json')
    with pytest.raises(d.Blocked,match='EXACT_MAIN_CI_NOT_FOUND'):r.verify_ci(0)
    assert r.report['ci_validation']['status']=='BLOCKED'


def test_untrusted_workflow_descriptor_or_stale_main_never_contacts_cloudflare(tmp_path):
    class Changed(RecordedGithub):
        def call(self,realm,method,path='',data=None,files=None):
            v=super().call(realm,method,path,data,files)
            if path=='/actions/workflows/regression.yml':v['path']='DUMMY/other.yml'
            return v
    r=d.Release(Changed(),FIXTURE['main_sha'],tmp_path/'report.json')
    with pytest.raises(d.Blocked,match='REGRESSION_WORKFLOW_UNVERIFIED'):r.verify_ci(0)
    r=d.Release(RecordedGithub(),NEW,tmp_path/'other.json')
    with pytest.raises(d.Blocked,match='STALE_MAIN_SHA'):r.verify_ci(0)


@pytest.mark.parametrize('count,rows',[(101,[]),(1,[])])
def test_incomplete_discovery_never_uses_partial_results(tmp_path,count,rows):
    class Changed(RecordedGithub):
        def call(self,realm,method,path='',data=None,files=None):
            if '/runs?' in path:return dict(total_count=count,workflow_runs=rows)
            return super().call(realm,method,path,data,files)
    r=d.Release(Changed(),FIXTURE['main_sha'],tmp_path/'report.json')
    with pytest.raises(d.Blocked,match='CI_DISCOVERY_INCOMPLETE'):r.verify_ci(0)


def test_manual_inspection_empty_ci_auto_resolves_and_still_has_zero_posts(tmp_path,monkeypatch):
    class AutoInspect(Fake):
        def call(self,realm,method,path='',data=None,files=None):
            if realm=='github' and '/workflows/42/runs?' in path:
                self.calls.append((realm,method,path,None))
                run=super().call('github','GET','/actions/runs/17')
                return dict(total_count=1,workflow_runs=[run])
            return super().call(realm,method,path,data,files)
    f=AutoInspect();f.close=lambda:None
    def remote(env,read_only=False):
        assert read_only is True
        return f
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('AURA_PRODUCTION_DEPLOY_ENABLED','false')
    monkeypatch.setattr(d,'Remote',remote)
    monkeypatch.setattr('sys.argv',['release','--sha',NEW,'--operation','inspect_worker'])
    assert d.main()==0
    report=json.loads(Path('release-results/deployment-report.json').read_text())
    assert report['status']=='WORKER_INSPECTED_NO_DEPLOYMENT'
    assert report['ci_validation']['status']=='PASS' and report['ci_run_id']==17 and report['mutations']==[]
    assert all(method=='GET' for _,method,_,_ in f.calls)
