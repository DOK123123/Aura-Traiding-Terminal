"""Issue38: optional flags/default representation, not historical root-cause claims."""
from copy import deepcopy
import json
import pytest
from scripts import deploy_active43_production as d
from scripts.active43_worker_evidence import runtime_profile,compatibility_flags_state
from tests.test_active43_production_deploy import release,Fake,V1,V2,NEW


def test_initial_failure_class_reproduced_from_existing_payload_materialization(tmp_path):
    f,r,s=release(tmp_path);before=deepcopy(f.settings)
    assert 'compatibility_flags' in before
    before.pop('compatibility_flags')
    payload=d.upload_metadata(before,NEW)
    assert payload['compatibility_flags']==[]
    after=deepcopy(before);after['compatibility_flags']=payload['compatibility_flags']
    # Old profile only sorted bindings: this rejected identical no-override config.
    def old_profile(value):
        value=deepcopy(value);value['bindings']=sorted(value['bindings'],key=lambda b:b['name']);return value
    assert old_profile(before)!=old_profile(after)
    assert d.profile(before)==d.profile(after)
    baseline=r.worker_state();baseline['settings']=d.profile(before)
    f.settings=after;r.invariant(baseline)
    assert not any(method=='POST' for _,method,_,_ in f.calls)


@pytest.mark.parametrize('left,right',[({},{}),({}, {'compatibility_flags':[]}),({'compatibility_flags':[]},{}),({'compatibility_flags':[]},{'compatibility_flags':[]})])
def test_missing_empty_equivalence_only_at_same_fixed_valid_date(left,right):
    a=dict(compatibility_date='2026-10-20',**left);b=dict(compatibility_date='2026-10-20',**right)
    original=deepcopy((a,b));assert d.equivalent(runtime_profile(a),runtime_profile(b))
    assert (a,b)==original


@pytest.mark.parametrize('value',[None,False,'DUMMY_FLAG',{},[1],['']])
def test_null_wrong_type_and_invalid_elements_never_become_empty(value):
    assert compatibility_flags_state({'compatibility_flags':value})=='INVALID'
    with pytest.raises(ValueError):runtime_profile(dict(compatibility_date='2026-10-20',compatibility_flags=value))


@pytest.mark.parametrize('before,after',[
    ({},{'compatibility_flags':['DUMMY_FLAG']}),
    ({'compatibility_flags':['DUMMY_FLAG']},{}),
    ({'compatibility_flags':['DUMMY_ONE']},{'compatibility_flags':['DUMMY_TWO']}),
    ({'compatibility_flags':['DUMMY_ONE','DUMMY_TWO']},{'compatibility_flags':['DUMMY_TWO','DUMMY_ONE']}),
])
def test_nonempty_or_changed_flags_are_not_discarded_or_reordered(before,after):
    a=runtime_profile(dict(compatibility_date='2026-10-20',**before))
    b=runtime_profile(dict(compatibility_date='2026-10-20',**after))
    assert not d.equivalent(a,b)


@pytest.mark.parametrize('value',[None,'','2026-99-99','2026-10-20T00:00:00Z',True])
def test_missing_or_invalid_date_does_not_authorize_optional_flags_normalization(value):
    with pytest.raises(ValueError):runtime_profile(dict(compatibility_date=value))
    with pytest.raises(ValueError):runtime_profile({})


def test_same_nonempty_flags_are_preserved_and_other_settings_not_normalized():
    a=dict(compatibility_date='2026-10-20',compatibility_flags=['DUMMY_FLAG'],limits={'cpu_ms':10})
    assert runtime_profile(a)==a and runtime_profile(a) is not a
    changed=deepcopy(a);changed['compatibility_date']='2026-10-21'
    assert d.runtime_comparison(a,changed)['equal'] is False
    changed=deepcopy(a);changed['limits']['cpu_ms']=11
    assert d.runtime_comparison(a,changed)['equal'] is False


@pytest.mark.parametrize('field,value',[('compatibility_flags',['DUMMY_PRIVATE_FLAG']),('compatibility_date','2026-10-21'),('limits',{'cpu_ms':19})])
def test_real_runtime_changes_still_block_before_activation(tmp_path,field,value):
    f,r,s=release(tmp_path);before=r.worker_state();f.settings[field]=value
    with pytest.raises(d.Blocked,match='WORKER_SETTINGS_CHANGED'):r.invariant(before)
    assert 'DUMMY_PRIVATE' not in json.dumps(r.report)


def test_post_upload_empty_array_materialization_no_longer_causes_false_settings_changed(tmp_path):
    f,r,s=release(tmp_path);f.settings.pop('compatibility_flags');f.resources['script_runtime'].pop('compatibility_flags')
    original=f.call
    def api(realm,method,path='',data=None,files=None):
        value=original(realm,method,path,data,files)
        if realm=='cf' and method=='POST' and path.startswith('/versions?'):
            f.settings['compatibility_flags']=[]
            # A response projection may now include the optional empty field.
            f.resources['script_runtime']['compatibility_flags']=[]
        return value
    f.call=api;r.deploy(17,s)
    assert r.report['status']=='DEPLOY_VERIFIED'
    assert f.active==V2


@pytest.mark.parametrize('current',['EMPTY','NONEMPTY','INVALID'])
def test_inspection_distinguishes_array_states_without_exposing_values(tmp_path,current):
    f,r,s=release(tmp_path);f.latest=V2
    f.resources['script_runtime'].pop('compatibility_flags')
    f.settings['compatibility_flags']=[] if current=='EMPTY' else ['DUMMY_PRIVATE_FLAG'] if current=='NONEMPTY' else None
    evidence=r.inspect_worker()
    assert evidence['compatibility_flags_states']==dict(current=current,active='MISSING',staged='MISSING')
    assert evidence['flags_representation_equivalent']==(current=='EMPTY')
    assert evidence['known_protected_config_matches']==(current=='EMPTY')
    assert evidence['safe_to_resume'] is False and evidence['activation_authorized'] is False
    assert not evidence['root_cause_confirmed'] and not evidence['secret_value_equality_verified']
    assert 'DUMMY_PRIVATE' not in json.dumps(evidence)
    assert all(method=='GET' for _,method,_,_ in f.calls)


def test_existing_staged_version_never_auto_activates_even_when_flags_equivalent(tmp_path):
    f,r,s=release(tmp_path);f.latest=V2;f.resources['script_runtime'].pop('compatibility_flags')
    with pytest.raises(d.Blocked,match='UNDEPLOYED_WORKER_VERSION_REQUIRES_REVIEW'):r.deploy(17,s)
    assert f.active==V1 and r.report['worker_diagnostics']['known_protected_config_matches']
    assert not any(method=='POST' for _,method,_,_ in f.calls)


def test_immutable_nonempty_flags_cannot_be_converted_to_missing_at_upload(tmp_path):
    f,r,s=release(tmp_path);f.settings['compatibility_flags']=['DUMMY_FLAG'];f.resources['script_runtime']['compatibility_flags']=['DUMMY_FLAG']
    original=f.call
    def api(realm,method,path='',data=None,files=None):
        value=original(realm,method,path,data,files)
        if realm=='cf' and path=='/versions/'+V2:value['resources']['script_runtime'].pop('compatibility_flags')
        return value
    f.call=api
    with pytest.raises(d.Blocked,match='STAGED_WORKER_CONFIG_CHANGED'):r.deploy(17,s)
    assert f.active==V1
