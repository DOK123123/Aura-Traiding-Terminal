"""Opt-in release controller. Tests inject a fake remote; default CLI never writes.

No exchange methods, trading controls, SQL, env changes or resource creation.
"""
import argparse
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid
import httpx
from scripts.active43_worker_evidence import differences, equivalent, runtime_profile, compatibility_flags_state

REPO='DOK123123/Aura-Traiding-Terminal'
WORKER='aura-ctive43-scheduler'
ORIGIN='https://aura-traiding-terminal.onrender.com'
CRON='2-59/5 * * * *'
SHA=re.compile('[a-f0-9]{40}')
UUID=re.compile('[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}')
CI_JOB='Python + JavaScript + isolated PostgreSQL'


class Blocked(Exception):
    pass


def require(ok,code):
    if not ok:raise Blocked(code)


def active_version(data):
    items=data['deployments']
    require(bool(items),'WORKER_DEPLOYMENT_UNVERIFIED')
    active=max(items,key=lambda d:d['created_on'])
    versions=active['versions']
    require(len(versions)==1 and versions[0]['percentage']==100,'SPLIT_WORKER_TRAFFIC')
    value=versions[0]['version_id']
    require(isinstance(value,str) and UUID.fullmatch(value),'WORKER_VERSION_UNVERIFIED')
    return value


def normalized_runtime(value):
    try:return runtime_profile(value)
    except ValueError:raise Blocked('WORKER_RUNTIME_FORMAT_UNVERIFIED') from None


def resources_profile(resources):
    require(isinstance(resources,dict),'VERSION_RESOURCES_UNVERIFIED')
    value=deepcopy(resources)
    value['script_runtime']=normalized_runtime(value.get('script_runtime'))
    return value


def runtime_comparison(before,after):
    try:
        result=differences(normalized_runtime(before),normalized_runtime(after))
        return dict(result,normalization='CF_OPTIONAL_FLAGS_EMPTY_V1',verified=True)
    except Blocked:
        return dict(equal=False,verified=False,normalization='CF_OPTIONAL_FLAGS_EMPTY_V1',
                    code='WORKER_RUNTIME_FORMAT_UNVERIFIED',values_redacted=True)


def profile(settings):
    value=normalized_runtime(settings)
    require(isinstance(value.get('bindings'),list),'BINDING_FORMAT_UNSUPPORTED')
    value['bindings']=sorted(value['bindings'],key=lambda b:b['name'])
    return value


def upload_metadata(settings,sha):
    settings=normalized_runtime(settings)
    bindings=settings['bindings']
    require(len({b['name'] for b in bindings})==len(bindings),'DUPLICATE_BINDINGS')
    by_name={b['name']:b for b in bindings}
    require(by_name.get('AURA_ACTIVE43_OPERATION',{}).get('text')=='saved_mode','WORKER_OPERATION_NOT_SAVED_MODE')
    require(by_name.get('AURA_ACTIVE43_CRON_ENABLED',{}).get('text')=='true','WORKER_CRON_NOT_ENABLED')
    require(by_name.get('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',{}).get('type')=='secret_text','SCHEDULER_SECRET_NOT_PRESENT')
    require(re.fullmatch(r'\d{4}-\d{2}-\d{2}',settings.get('compatibility_date','')),'RUNTIME_UNVERIFIED')
    # Unsupported execution resources must be reviewed, not silently dropped.
    require(not settings.get('placement') and not settings.get('tail_consumers') and not settings.get('migration_tag'),
            'UNSUPPORTED_RUNTIME_SETTINGS')
    metadata=dict(main_module='worker.mjs',bindings=[dict(name=b['name'],type='inherit') for b in bindings],
        compatibility_date=settings['compatibility_date'],compatibility_flags=settings.get('compatibility_flags',[]),
        annotations={'workers/commit_sha':sha,'workers/message':'Aura paper-only release '+sha})
    for key in ('limits','usage_model'):
        if key in settings:metadata[key]=deepcopy(settings[key])
    return metadata


class Remote:
    """Fixed hosts, no redirects, no unsafe POST retries, bounded responses."""
    def __init__(self,env,read_only=False):
        self.read_only=read_only
        self.service=env.get('AURA_RENDER_SERVICE_ID','');self.account=env.get('AURA_CLOUDFLARE_ACCOUNT_ID','')
        require(re.fullmatch('srv-[a-z0-9]{10,40}',self.service),'RENDER_SERVICE_ID_MISSING_OR_INVALID')
        require(re.fullmatch('[a-f0-9]{32}',self.account),'CLOUDFLARE_ACCOUNT_ID_MISSING_OR_INVALID')
        names=('AURA_RENDER_API_KEY','AURA_CLOUDFLARE_API_TOKEN','AURA_TESTNET_VIEW_PASSWORD','GITHUB_TOKEN')
        require(all(isinstance(env.get(k),str) and 0<len(env[k])<=8192 for k in names),'DEPLOY_CREDENTIALS_NOT_CONFIGURED')
        require(all(env[k]==env[k].strip() and env[k].isascii() and env[k].isprintable()
                    for k in (names[0],names[1],names[3])),'DEPLOY_TOKEN_FORMAT_INVALID')
        self.headers={
            'render':{'Authorization':'Bearer '+env[names[0]]},
            'cf':{'Authorization':'Bearer '+env[names[1]]},
            'aura':{'Authorization':'Basic '+base64.b64encode(('aura:'+env[names[2]]).encode()).decode()},
            'github':{'Authorization':'Bearer '+env[names[3]],'Accept':'application/vnd.github+json'}}
        self.bases=dict(render='https://api.render.com/v1/services/'+self.service,
            cf='https://api.cloudflare.com/client/v4/accounts/'+self.account+'/workers/scripts/'+WORKER,
            aura=ORIGIN,github='https://api.github.com/repos/'+REPO)
        self.client=httpx.Client(timeout=55,follow_redirects=False)

    def close(self):self.client.close()

    def call(self,realm,method,path='',data=None,files=None):
        require(realm in self.bases and (path=='' or path.startswith(('/', '?'))),'INVALID_API_TARGET')
        require(not self.read_only or method=='GET','READ_ONLY_INSPECTION_WRITE_FORBIDDEN')
        require(method=='GET' or method=='POST' and ((realm=='render' and path=='/deploys') or
            (realm=='cf' and path in ('/versions?bindings_inherit=strict','/deployments'))),'API_WRITE_FORBIDDEN')
        require('://' not in path and '..' not in path,'INVALID_API_TARGET')
        if realm=='aura':
            require(path in ('/api/health','/api/active43/deployment-readiness','/api/active43/paper-readiness'),
                    'AURA_READ_METHOD_FORBIDDEN')
        for attempt in range(3 if method=='GET' else 1):
            try:
                with self.client.stream(method,self.bases[realm]+path,headers=self.headers[realm],
                        json=data if files is None else None,files=files) as response:
                    raw=bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        require(len(raw)<=4*1024*1024,'API_RESPONSE_TOO_LARGE')
                    if method=='GET' and response.status_code in (429,502,503,504) and attempt<2:
                        retry=response.headers.get('Retry-After','2')
                        require(re.fullmatch('[0-9]{1,2}',retry) and int(retry)<=60,'RETRY_AFTER_REQUIRES_REVIEW')
                        time.sleep(max(2,int(retry)));continue
                    require(200<=response.status_code<300,realm.upper()+'_HTTP_'+str(response.status_code))
                    value=json.loads(raw)
                    if realm=='cf':
                        require(value.get('success') is True,'CLOUDFLARE_API_REJECTED')
                        value=value['result']
                    return value
            except httpx.HTTPError:
                if method=='GET' and attempt<2:
                    time.sleep(2);continue
                raise Blocked(realm.upper()+('_WRITE_OUTCOME_UNKNOWN' if method!='GET' else '_READ_UNAVAILABLE')) from None
            except ValueError:
                raise Blocked(realm.upper()+('_WRITE_OUTCOME_UNKNOWN' if method!='GET' else '_INVALID_RESPONSE')) from None


class Release:
    def __init__(self,remote,sha,report,clock=time.time,sleep=time.sleep):
        require(bool(SHA.fullmatch(sha)),'INVALID_RELEASE_SHA')
        self.r=remote;self.sha=sha;self.path=Path(report);self.clock=clock;self.sleep=sleep
        self.report=dict(status='BLOCKED',release_sha=sha,worker_name=WORKER,production_paper_verified=False,
            mutations=[],automatic_ticks=[],started_at=int(clock()))
        self.baseline=None

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.path.write_text(json.dumps(self.report,indent=2)+'\n')
        # Keep rollback IDs in logs even if the runner is hard-cancelled before
        # artifact upload. Never print credentials, settings or account data.
        print(json.dumps(dict(event='RELEASE_CHECKPOINT',**{k:self.report[k] for k in (
            'status','release_sha','previous_render_commit','previous_worker_version_id',
            'render_deploy_id','render_commit','render_live_commit','staged_worker_version_id','worker_version_id',
            'existing_staged_worker_version_id','worker_diagnostics','comparison_failures','ci_validation','mutations')
            if k in self.report})),flush=True)

    def main_head(self):
        return self.r.call('github','GET','/commits/main')['sha']

    def verify_ci(self,run_id):
        """Exact trusted checkout CI; empty input discovers only that SHA's push CI."""
        evidence=dict(status='BLOCKED',selection='EXPLICIT' if run_id else 'EXACT_SHA_DISCOVERY',
                      expected_head_sha=self.sha,checks={},failed_checks=[])
        self.report['ci_validation']=evidence
        def check(name,ok,code):
            evidence['checks'][name]=bool(ok)
            if not ok:
                evidence['failed_checks'].append(name);self.save();raise Blocked(code)
        def safe_id(value):return value if type(value) is int and value>0 else None
        def safe_sha(value):return value if isinstance(value,str) and SHA.fullmatch(value) else None
        observed_main=self.main_head();evidence['observed_main_sha']=safe_sha(observed_main)
        check('checkout_is_current_main',observed_main==self.sha,'STALE_MAIN_SHA')
        workflow=self.r.call('github','GET','/actions/workflows/regression.yml')
        expected_id=safe_id(workflow.get('id'));evidence['expected_workflow_id']=expected_id
        check('trusted_workflow_descriptor',expected_id is not None and workflow.get('path')=='.github/workflows/regression.yml'
              and workflow.get('state')=='active','REGRESSION_WORKFLOW_UNVERIFIED')
        check('run_id_is_valid',type(run_id) is int and run_id>=0,'CI_RUN_ID_REQUIRED')
        if run_id==0:
            listing=self.r.call('github','GET','/actions/workflows/'+str(expected_id)+
                '/runs?branch=main&event=push&head_sha='+self.sha+'&status=completed&per_page=100')
            check('discovery_complete',type(listing.get('total_count')) is int and 0<=listing['total_count']<=100
                  and isinstance(listing.get('workflow_runs'),list) and len(listing['workflow_runs'])==listing['total_count'],
                  'CI_DISCOVERY_INCOMPLETE')
            candidates=[r for r in listing['workflow_runs'] if isinstance(r,dict) and safe_id(r.get('id')) is not None
                and r.get('head_sha')==self.sha and r.get('head_branch')=='main' and r.get('event')=='push'
                and safe_id(r.get('workflow_id'))==expected_id and isinstance(r.get('head_repository'),dict) and r['head_repository'].get('full_name')==REPO
                and r.get('status')=='completed' and r.get('conclusion')=='success']
            check('exact_sha_success_candidate',bool(candidates),'EXACT_MAIN_CI_NOT_FOUND')
            run_id=max(r['id'] for r in candidates)
        evidence['run_id']=run_id
        run=self.r.call('github','GET','/actions/runs/'+str(run_id))
        evidence.update(actual_head_sha=safe_sha(run.get('head_sha')),actual_workflow_id=safe_id(run.get('workflow_id')),
            run_event=run.get('event') if run.get('event') in ('push','pull_request','workflow_dispatch','workflow_run') else 'UNVERIFIED',
            run_branch='main' if run.get('head_branch')=='main' else 'UNVERIFIED',
            run_status=run.get('status') if run.get('status') in ('completed','in_progress','queued') else 'UNVERIFIED',
            run_conclusion=run.get('conclusion') if run.get('conclusion') in ('success','failure','skipped','cancelled','timed_out') else 'UNVERIFIED')
        identity=dict(run_id_matches_request=safe_id(run.get('id'))==run_id,run_head_sha=run.get('head_sha')==self.sha,run_branch=run.get('head_branch')=='main',
            run_event=run.get('event')=='push',run_repository=isinstance(run.get('head_repository'),dict) and run['head_repository'].get('full_name')==REPO,
            run_workflow_id=safe_id(run.get('workflow_id'))==expected_id,run_completed=run.get('status')=='completed',
            run_success=run.get('conclusion')=='success')
        evidence['checks'].update(identity)
        failures=[k for k,v in identity.items() if not v]
        if failures:
            evidence['failed_checks'].extend(failures);self.save();raise Blocked('EXACT_MAIN_CI_NOT_SUCCESSFUL')
        jobs=self.r.call('github','GET','/actions/runs/'+str(run_id)+'/jobs?filter=latest&per_page=100')
        check('one_complete_regression_job',type(jobs.get('total_count')) is int and jobs['total_count']==1
              and isinstance(jobs.get('jobs'),list) and len(jobs['jobs'])==1 and isinstance(jobs['jobs'][0],dict),
              'CI_JOBS_INCOMPLETE_OR_UNEXPECTED')
        required=[j for j in jobs['jobs'] if j['name']==CI_JOB]
        evidence['expected_job_name']=CI_JOB
        check('regression_job_name',len(required)==1,'REGRESSION_JOB_NOT_SUCCESSFUL')
        check('regression_job_completed_success',required[0].get('status')=='completed' and required[0].get('conclusion')=='success',
              'REGRESSION_JOB_NOT_SUCCESSFUL')
        check('regression_steps_present',isinstance(required[0].get('steps'),list),'REGRESSION_STEP_NOT_SUCCESSFUL')
        for name in ('Run actual regressions with no external network and no production secrets','Upload actual test reports'):
            check('step:'+name,any(isinstance(s,dict) and s.get('name')==name and s.get('status')=='completed' and s.get('conclusion')=='success'
                for s in required[0]['steps']),'REGRESSION_STEP_NOT_SUCCESSFUL')
        environment=self.r.call('github','GET','/environments/production')
        policy=environment.get('deployment_branch_policy') or {}
        check('production_environment_selected_branches',policy.get('custom_branch_policies') is True and policy.get('protected_branches') is False,
              'PRODUCTION_ENV_MAIN_ONLY_POLICY_REQUIRED')
        branches=self.r.call('github','GET','/environments/production/deployment-branch-policies?per_page=100')
        check('production_environment_main_only',branches.get('total_count')==1 and len(branches.get('branch_policies',[]))==1
            and branches['branch_policies'][0].get('name')=='main' and branches['branch_policies'][0].get('type','branch')=='branch',
            'PRODUCTION_ENV_MAIN_ONLY_POLICY_REQUIRED')
        evidence['status']='PASS';self.report['ci_run_id']=run_id;self.save()

    def off(self,expected_commit=None):
        body=self.r.call('aura','GET','/api/active43/deployment-readiness')
        account=body.get('account') or {}
        require(body.get('scope')=='AURA43_ACTIVE_PAPER' and body.get('read_only') is True
            and body.get('state_changed') is False and body.get('paper_only') is True
            and body.get('exchange_execution') is False and body.get('status')=='PASS'
            and body.get('errors')==[] and type(body.get('checked_at')) is int
            and -3<=self.clock()-body['checked_at']<=60,'READ_ONLY_ACCOUNT_GATE_BLOCKED')
        require(account.get('mode')=='OFF' and type(account.get('open_positions')) is int and account['open_positions']==0
            and type(account.get('pending_operations')) is int and account['pending_operations']==0
            and 'risk_code' in account and account['risk_code'] is None
            and re.fullmatch('[a-f0-9]{64}',account.get('ledger_sha256','')),'EMPTY_OFF_ACCOUNT_NOT_CONFIRMED')
        require(isinstance(body.get('render_commit'),str) and SHA.fullmatch(body['render_commit']),'RENDER_COMMIT_UNVERIFIED')
        if expected_commit:require(body['render_commit']==expected_commit,'RENDER_COMMIT_MISMATCH')
        fingerprint=account['ledger_sha256']
        if self.baseline is None:self.baseline=fingerprint
        else:require(fingerprint==self.baseline,'FINANCIAL_LEDGER_CHANGED')
        return body

    def render_state(self):
        svc=self.r.call('render','GET')
        require(svc.get('type')=='web_service' and svc.get('branch')=='main'
            and svc.get('repo','').removesuffix('.git')=='https://github.com/'+REPO
            and svc.get('serviceDetails',{}).get('url')==ORIGIN,'RENDER_SERVICE_IDENTITY_MISMATCH')
        require(svc['autoDeployTrigger']=='off' if 'autoDeployTrigger' in svc else svc.get('autoDeploy')=='no',
                'RENDER_AUTO_DEPLOY_MUST_BE_OFF')
        deployments=self.r.call('render','GET','/deploys?limit=100')
        require(not any(d['deploy']['status'] in ('created','build_in_progress','pre_deploy_in_progress','update_in_progress') for d in deployments),'RENDER_DEPLOY_ALREADY_RUNNING')
        live=[d['deploy'] for d in deployments if d['deploy']['status']=='live']
        require(len(live)==1 and SHA.fullmatch(live[0]['commit']['id']),'RENDER_LIVE_SHA_UNVERIFIED')
        return live[0]['commit']['id'],deployments

    def worker_state(self):
        active=active_version(self.r.call('cf','GET','/deployments'))
        versions=self.r.call('cf','GET','/versions?per_page=100')['items']
        require(bool(versions),'WORKER_VERSIONS_UNVERIFIED')
        latest=max(versions,key=lambda v:v['number'])['id']
        require(isinstance(latest,str) and UUID.fullmatch(latest),'WORKER_VERSION_UNVERIFIED')
        if latest!=active:
            self.report['existing_staged_worker_version_id']=latest
            self.inspect_worker(latest)
            raise Blocked('UNDEPLOYED_WORKER_VERSION_REQUIRES_REVIEW')
        settings=self.r.call('cf','GET','/settings')
        upload_metadata(settings,self.sha)
        schedules=self.r.call('cf','GET','/schedules')
        require([v['cron'] for v in schedules['schedules']]==[CRON],'CRON_MISMATCH')
        domain=self.r.call('cf','GET','/subdomain')
        version=self.r.call('cf','GET','/versions/'+active)
        require(version.get('id')==active and isinstance(version.get('resources',{}).get('script_runtime'),dict)
            and 'bindings' in version['resources'],'VERSION_RESOURCES_UNVERIFIED')
        return dict(active=active,settings=profile(settings),schedules=schedules,subdomain=domain,
                    resources=resources_profile(version['resources']))

    def compare(self,label,before,after,code):
        if equivalent(before,after):return
        self.report.setdefault('comparison_failures',[]).append(dict(
            component=label,code=code,**differences(before,after)))
        self.save()
        raise Blocked(code)

    def inspect_worker(self,staged_id=None):
        """Only GET. No automatic resume, activation, upload or guessed repair."""
        active=active_version(self.r.call('cf','GET','/deployments'))
        versions=self.r.call('cf','GET','/versions?per_page=100')['items']
        require(bool(versions),'WORKER_VERSIONS_UNVERIFIED')
        latest=max(versions,key=lambda v:v['number'])['id']
        require(isinstance(latest,str) and UUID.fullmatch(latest),'WORKER_VERSION_UNVERIFIED')
        candidate=staged_id or latest
        require(isinstance(candidate,str) and UUID.fullmatch(candidate),'INVALID_INSPECTION_VERSION')
        active_data=self.r.call('cf','GET','/versions/'+active)
        staged_data=self.r.call('cf','GET','/versions/'+candidate)
        require(active_data.get('id')==active and staged_data.get('id')==candidate,'VERSION_RESOURCES_UNVERIFIED')
        current=self.r.call('cf','GET','/settings')
        protected={key:differences(active_data.get('resources',{}).get(key),
            staged_data.get('resources',{}).get(key)) for key in ('bindings','script_runtime')}
        runtime_keys=('compatibility_date','compatibility_flags','limits','usage_model')
        current_runtime={k:current[k] for k in runtime_keys if k in current}
        active_runtime={k:active_data.get('resources',{}).get('script_runtime',{})[k]
            for k in runtime_keys if k in active_data.get('resources',{}).get('script_runtime',{})}
        staged_runtime={k:staged_data.get('resources',{}).get('script_runtime',{})[k]
            for k in runtime_keys if k in staged_data.get('resources',{}).get('script_runtime',{})}
        schedules=self.r.call('cf','GET','/schedules')
        evidence=dict(active_version_id=active,latest_version_id=latest,inspected_version_id=candidate,
            unactivated_version_present=latest!=active,read_only=True,root_cause_confirmed=False,secret_value_equality_verified=False,
            active_staged_resources=protected,
            current_vs_active_runtime=differences(active_runtime,current_runtime),
            current_vs_staged_runtime=differences(staged_runtime,current_runtime),
            current_vs_active_bindings=differences(active_data.get('resources',{}).get('bindings'),current.get('bindings')),
            current_vs_staged_bindings=differences(staged_data.get('resources',{}).get('bindings'),current.get('bindings')),
            current_cron_matches_expected=[v.get('cron') for v in schedules.get('schedules',[])]==[CRON],
            safe_to_resume=False,resume_code='REVIEW_REQUIRED_NO_AUTOMATIC_POST',
            missing_evidence='FAILED_RUN_PRE_UPLOAD_SETTINGS_SNAPSHOT_NOT_CAPTURED')
        # Recheck stability; observing two stable reads does NOT reconstruct the
        # settings snapshot that the failed historic run never persisted.
        evidence['inspection_settings_stable']=differences(current,self.r.call('cf','GET','/settings'))
        require(active_version(self.r.call('cf','GET','/deployments'))==active,'WORKER_CHANGED_DURING_INSPECTION')
        # Keep raw diffs for forensic context, alongside the narrow semantic rule.
        active_full=active_data.get('resources',{}).get('script_runtime')
        staged_full=staged_data.get('resources',{}).get('script_runtime')
        evidence['compatibility_flags_states']=dict(current=compatibility_flags_state(current),
            active=compatibility_flags_state(active_full),staged=compatibility_flags_state(staged_full))
        evidence['normalized_runtime_comparisons']=dict(
            active_staged=runtime_comparison(active_full,staged_full),
            current_active=runtime_comparison(active_runtime,current_runtime),
            current_staged=runtime_comparison(staged_runtime,current_runtime))
        normalized=evidence['normalized_runtime_comparisons']
        evidence['flags_representation_equivalent']=(all(v in ('MISSING','EMPTY') for v in evidence['compatibility_flags_states'].values())
            and all(v.get('verified') is True and v['equal'] for v in normalized.values()))
        evidence['known_protected_config_matches']=(all(v.get('verified') is True and v['equal'] for v in normalized.values())
            and evidence['current_cron_matches_expected'] and evidence['inspection_settings_stable']['equal']
            and protected['bindings']['equal'] and evidence['current_vs_active_bindings']['equal']
            and evidence['current_vs_staged_bindings']['equal'])
        evidence['historical_limitations']=['HISTORIC_PRE_UPLOAD_SETTINGS_MISSING','OLD_ARRAY_CONTENT_NOT_LOGGED']
        evidence['activation_authorized']=False
        evidence['activation_blockers']=['EXPLICIT_OWNER_AUTHORIZATION_REQUIRED','CURRENT_SETTINGS_BASELINE_REVIEW_REQUIRED',
                                          'SECRET_VALUES_NOT_OBSERVABLE','STAGED_SOURCE_REVIEW_REQUIRED']
        self.report['worker_diagnostics']=evidence;self.save()
        return evidence

    def invariant(self,baseline,allow_new_version=False):
        current=self.r.call('cf','GET','/settings')
        try:normalized=profile(current)
        except Exception:
            self.compare('settings_format',baseline['settings'],current,'WORKER_SETTINGS_CHANGED')
            raise
        self.compare('settings',baseline['settings'],normalized,'WORKER_SETTINGS_CHANGED')
        for path,key in (('/schedules','schedules'),('/subdomain','subdomain')):
            self.compare(key,baseline[key],self.r.call('cf','GET',path),'WORKER_ROUTING_OR_CRON_CHANGED')
        if not allow_new_version:
            require(active_version(self.r.call('cf','GET','/deployments'))==baseline['active'],'WORKER_DEPLOYMENT_CHANGED')

    def render_deploy(self,target):
        self.off();self.report['mutations'].append('RENDER_DEPLOY_REQUESTED');self.save()
        response=self.r.call('render','POST','/deploys',dict(commitId=target,clearCache='do_not_clear'))
        deploy_id=response['id'];require(re.fullmatch('dep-[a-z0-9]{10,40}',deploy_id),'RENDER_DEPLOY_ID_UNVERIFIED')
        self.report['render_deploy_id']=deploy_id;self.save()
        deadline=self.clock()+1200
        while self.clock()<deadline:
            value=self.r.call('render','GET','/deploys/'+deploy_id)
            require(value['commit']['id']==target,'RENDER_DEPLOY_COMMIT_MISMATCH')
            if value['status']=='live':break
            require(value['status'] in ('created','build_in_progress','pre_deploy_in_progress','update_in_progress'),'RENDER_DEPLOY_FAILED')
            self.sleep(15)
        else:raise Blocked('RENDER_DEPLOY_TIMEOUT')
        self.report['render_live_commit']=target;self.save()
        deadline=self.clock()+180
        while self.clock()<deadline:
            try:
                require(self.r.call('aura','GET','/api/health').get('status')=='ok','HEALTH_NOT_OK')
                self.off(target);break
            except Blocked as exc:
                if str(exc) in ('FINANCIAL_LEDGER_CHANGED','EMPTY_OFF_ACCOUNT_NOT_CONFIRMED'):raise
                self.sleep(10)
        else:raise Blocked('RENDER_COMMIT_OR_HEALTH_NOT_CONFIRMED')
        self.report['render_commit']=target;self.save()

    def activate(self,version):
        self.off();self.report['mutations'].append('WORKER_ACTIVATION_REQUESTED');self.save()
        self.r.call('cf','POST','/deployments',dict(strategy='percentage',versions=[dict(version_id=version,percentage=100)]))
        require(active_version(self.r.call('cf','GET','/deployments'))==version,'WORKER_ACTIVATION_UNVERIFIED')
        self.report['worker_version_id']=version;self.report['worker_activated_at']=int(self.clock());self.save()

    def verify_ticks(self):
        deadline=self.clock()+1050
        while self.clock()<deadline:
            body=self.off(self.sha);scheduler=body.get('scheduler') or {}
            ticks=scheduler.get('ticks') or []
            if (scheduler.get('status')=='PASS' and len(ticks)==2 and len({t['tick_id'] for t in ticks})==2
                and ticks[0]['scheduled_at']-ticks[1]['scheduled_at']==300
                and all(t.get('render_commit')==self.sha and t['scheduled_at']>self.report['worker_activated_at']
                    and t.get('status')=='COMPLETED' and t.get('state_saved') is True and t.get('mode')=='OFF'
                    and t.get('opened')==0 and t.get('closed')==0 for t in ticks)):
                self.report['automatic_ticks']=[{k:t[k] for k in ('tick_id','scheduled_at','created_at','render_commit')} for t in ticks]
                return
            self.sleep(30)
        raise Blocked('TWO_POST_DEPLOY_AUTOMATIC_TICKS_NOT_CONFIRMED')

    def deploy(self,ci_run_id,worker_file):
        self.verify_ci(ci_run_id)
        prior,_=self.render_state();self.off(prior);baseline=self.worker_state()
        self.report.update(status='DEPLOYING',previous_render_commit=prior,previous_worker_version_id=baseline['active']);self.save()
        require(self.main_head()==self.sha,'STALE_MAIN_SHA')
        if prior!=self.sha:self.render_deploy(self.sha)
        else:
            require(self.r.call('aura','GET','/api/health').get('status')=='ok','HEALTH_NOT_OK')
            self.report['render_commit']=self.sha
        self.off(self.sha);self.invariant(baseline)
        require(self.main_head()==self.sha,'STALE_MAIN_SHA')
        # latest uploaded must still be the active baseline before strict inheritance.
        require(equivalent(self.worker_state(),baseline),'WORKER_BASELINE_CHANGED')
        source=Path(worker_file).read_bytes();require(0<len(source)<128000,'WORKER_SOURCE_SIZE_INVALID')
        self.report['worker_source_sha256']=hashlib.sha256(source).hexdigest()
        metadata=upload_metadata(baseline['settings'],self.sha)
        self.report['mutations'].append('WORKER_VERSION_UPLOAD_REQUESTED');self.save()
        uploaded=self.r.call('cf','POST','/versions?bindings_inherit=strict',files={
            'metadata':(None,json.dumps(metadata),'application/json'),
            'worker.mjs':('worker.mjs',source,'application/javascript+module')})
        candidate=uploaded['id'];require(UUID.fullmatch(candidate),'WORKER_UPLOAD_UNVERIFIED')
        self.report['staged_worker_version_id']=candidate;self.save()
        self.invariant(baseline)
        candidate_state=self.r.call('cf','GET','/versions/'+candidate)
        require(candidate_state.get('id')==candidate,'STAGED_WORKER_VERSION_UNVERIFIED')
        for key in ('bindings','script_runtime'):
            self.compare('staged_'+key,baseline['resources'][key],resources_profile(candidate_state.get('resources',{})).get(key),
                         'STAGED_WORKER_CONFIG_CHANGED')
        self.off(self.sha);require(self.main_head()==self.sha,'STALE_MAIN_SHA')
        self.activate(candidate);self.invariant(baseline,True)
        self.verify_ticks()
        ready=self.r.call('aura','GET','/api/active43/paper-readiness')
        require(ready.get('status')=='READY' and ready.get('scope')=='AURA43_ACTIVE_PAPER'
            and ready.get('read_only') is True and ready.get('state_changed') is False
            and ready.get('paper_only') is True and ready.get('exchange_execution') is False
            and ready.get('errors')==[] and ready.get('account',{}).get('mode')=='OFF'
            and ready.get('market',{}).get('status')=='PASS' and ready['market'].get('history_complete') is True
            and ready['market'].get('last_closed_at')==int(self.clock())//300*300,'PAPER_READINESS_BLOCKED')
        self.off(self.sha);self.invariant(baseline,True)
        require(active_version(self.r.call('cf','GET','/deployments'))==candidate,'WORKER_VERSION_CHANGED_DURING_VERIFICATION')
        self.report.update(status='DEPLOY_VERIFIED',account_and_history_unchanged=True,
                           cloudflare_audit_verified=False,http_delivery_verified=False,
                           route_inventory_verified=False,routes_unchanged_by_design=True)

    def rollback(self,old_sha,old_version,confirmation):
        require(SHA.fullmatch(old_sha or '') and UUID.fullmatch(old_version or ''),'ROLLBACK_TARGETS_REQUIRED')
        require(confirmation=='ROLLBACK PAPER OFF NO CONFIG ROTATION','ROLLBACK_CONFIRMATION_REQUIRED')
        require(self.main_head()==self.sha,'STALE_MAIN_SHA')
        ancestry=self.r.call('github','GET','/compare/'+old_sha+'...'+self.sha)
        require(ancestry.get('status') in ('ahead','identical') and ancestry.get('merge_base_commit',{}).get('sha')==old_sha,
                'ROLLBACK_SHA_NOT_MAIN_ANCESTOR')
        current,deployments=self.render_state();self.off(current);baseline=self.worker_state()
        require(any(d['deploy']['commit']['id']==old_sha for d in deployments),'ROLLBACK_RENDER_SHA_NOT_IN_HISTORY')
        version=self.r.call('cf','GET','/versions/'+old_version)
        require(version['id']==old_version,'ROLLBACK_WORKER_VERSION_UNVERIFIED')
        # No automatic rollback of bindings/runtime to an incompatible profile.
        require(all(equivalent(resources_profile(version.get('resources',{})).get(k),baseline['resources'][k])
            for k in ('bindings','script_runtime')),'ROLLBACK_BINDINGS_OR_RUNTIME_REQUIRE_MANUAL_REVIEW')
        self.report.update(status='ROLLING_BACK',previous_render_commit=current,previous_worker_version_id=baseline['active']);self.save()
        self.activate(old_version);self.invariant(baseline,True)
        self.render_deploy(old_sha);self.off(old_sha)
        self.report.update(status='ROLLBACK_VERIFIED',account_and_history_unchanged=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation',choices=['deploy','rollback','inspect_worker'],default='deploy')
    parser.add_argument('--sha',required=True);parser.add_argument('--ci-run-id',type=int,default=0)
    parser.add_argument('--rollback-sha',default='');parser.add_argument('--rollback-version',default='')
    parser.add_argument('--rollback-confirmation',default='');parser.add_argument('--execute',action='store_true')
    parser.add_argument('--inspect-version',default='')
    args=parser.parse_args();remote=None;release=None
    try:
        inspection=args.operation=='inspect_worker'
        require(inspection or args.execute and os.getenv('AURA_PRODUCTION_DEPLOY_ENABLED')=='true','DEPLOY_NOT_AUTHORIZED')
        remote=Remote(os.environ,read_only=inspection);release=Release(remote,args.sha,'release-results/deployment-report.json')
        release.report['operation']=args.operation
        if inspection:
            release.verify_ci(args.ci_run_id)
            release.inspect_worker(args.inspect_version or None)
            release.report['status']='WORKER_INSPECTED_NO_DEPLOYMENT'
        elif args.operation=='deploy':release.deploy(args.ci_run_id,Path(__file__).resolve().parents[1]/'deploy/active43-free-worker/worker.mjs')
        else:
            release.verify_ci(args.ci_run_id)
            release.rollback(args.rollback_sha,args.rollback_version,args.rollback_confirmation)
        release.save();print(json.dumps(dict(status=release.report['status'],release_sha=args.sha)))
    except Exception as exc:
        code=str(exc) if isinstance(exc,Blocked) and re.fullmatch('[A-Z0-9_]{1,100}',str(exc)) else 'RELEASE_CONTROLLER_FAILED'
        report=release.report if release else dict(status='BLOCKED',mutations=[])
        failure_status='INSPECTION_BLOCKED' if args.operation=='inspect_worker' else 'DEPLOY_BLOCKED'
        report.update(status=failure_status,code=code,manual_reconciliation_required=bool(report['mutations']) or bool(report.get('existing_staged_worker_version_id')))
        Path('release-results').mkdir(exist_ok=True);Path('release-results/deployment-report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(status=failure_status,code=code)));return 1
    finally:
        if remote:remote.close()
    return 0

if __name__=='__main__':raise SystemExit(main())
