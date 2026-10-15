"""Offline connection diagnostics; no real credentials or database calls."""
import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from app.automated.diagnostics import configuration,connection_evidence,error_category,http_error
from app.automated.service import configured

@pytest.mark.parametrize('value',[None,[],{},123,'untrusted-secret'])
def test_malformed_error_code_is_not_echoed_or_crashes(value):
    assert http_error(401,{'code':value})==('STORAGE_AUTH',None)

@pytest.mark.parametrize('code,category',[
    ('STORAGE_DNS','DNS_ERROR'),('STORAGE_TIMEOUT','NETWORK_ERROR'),
    ('STORAGE_AUTH','AUTH_ERROR'),('STORAGE_DATABASE_UNAVAILABLE','DATABASE_ERROR'),
    ('STORAGE_SCHEMA_MISSING','SCHEMA_ERROR'),('INVALID_STORAGE_CONFIGURATION','CONFIG_ERROR')])
def test_categories(code,category):
    assert error_category(code)==category

def test_hostname_is_instantiated_client_not_changed_environment():
    store=SimpleNamespace(transport=SimpleNamespace(base='https://abcdefghijklmnopqrst.supabase.co'))
    with patch.dict('os.environ',{'AURA_AUTO42_SUPABASE_URL':'https://differentprojectabcd.supabase.co'}):
        assert connection_evidence(store)['hostname']=='abcdefghijklmnopqrst.supabase.co'
    store.transport.base='https://dummy-secret@invalid/rest/v1?key=dummy-secret'
    assert connection_evidence(store)['hostname'] is None

def test_generic_environment_does_not_silently_select_another_database():
    with patch.dict('os.environ',{'SUPABASE_URL':'https://abcdefghijklmnopqrst.supabase.co','SUPABASE_SERVICE_ROLE_KEY':'dummy-secret'},clear=True):
        c=configuration()
        assert 'AURA_AUTO42_SUPABASE_URL' in c['missing_variables']
        assert 'SUPABASE_URL' in c['ignored_generic_variables']
        svc=configured(None)
        assert svc.store is None
        assert svc.diagnostics(error=svc.reason)['storage']['error_category']=='CONFIG_ERROR'
        assert 'dummy-secret' not in json.dumps(c)

@pytest.mark.parametrize('suffix',['/rest/v1','/rest/v1/','/','?key=dummy-secret'])
def test_non_project_url_rejected_without_network(suffix):
    with patch.dict('os.environ',{'AURA_AUTO42_SUPABASE_URL':'https://abcdefghijklmnopqrst.supabase.co'+suffix,'AURA_AUTO42_SUPABASE_SERVICE_KEY':'dummy-key-for-offline-unit-test-only'},clear=True):
        svc=configured(None)
        assert svc.store is None
        assert svc.reason=='INVALID_STORAGE_CONFIGURATION'
