import json
from scripts.active43_scheduler import run,verified,URL

class Response:
    status=200
    def __init__(self,body):self.body=body
    def read(self,n):return json.dumps(self.body).encode()[:n]
    def __enter__(self):return self
    def __exit__(self,*a):pass

class Opener:
    def __init__(self,body):self.body=body;self.requests=[]
    def open(self,req,timeout):self.requests.append(req);return Response(self.body)

def body():return dict(status='COMPLETED',scope='AURA43_ACTIVE_PAPER',market_source='Bitget · USDT-M Futures / api.bitget.com',strategy_version='AURA_4.3_ACTIVE_PAPER_3',paper_only=True,exchange_execution=False,state_saved=True,processed=True,duplicate=False,mode='ON',opened=1,closed=0,last_processed_closed_at=1800000000)

def test_scheduler_fixed_namespace_and_safe_output():
    opener=Opener(body());messages=[];token='DUMMY_ACTIVE43_SCHEDULER_ONLY_'+'x'*40
    assert run({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':token},opener=opener,emit=messages.append)==0
    assert len(opener.requests)==1 and opener.requests[0].full_url==URL
    assert opener.requests[0].get_method()=='POST' and '/api/active43/tick' in URL
    assert token not in '\n'.join(messages) and 'apikey' not in '\n'.join(messages)

def test_scheduler_rejects_unconfigured_unsafe_ambiguous_or_wrong_portfolio():
    assert run({},opener=Opener(body()),emit=lambda _:None)==1
    for change in (dict(scope='AURA42'),dict(market_source='Binance Spot'),dict(strategy_version='AURA_4.3_ACTIVE_PAPER_1'),dict(exchange_execution=True),dict(state_saved=False),dict(status='PAUSED'),dict(opened=2),dict(processed=True,last_processed_closed_at=None)):
        b=body();b.update(change);assert not verified(b)
        assert run({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':'DUMMY_'+'x'*40},opener=Opener(b),emit=lambda _:None,sleep=lambda _:None)==1


def test_diagnostic_dispatch_never_calls_tick_even_when_response_says_on():
    from scripts.active43_scheduler import DIAGNOSTIC_URL,diagnostic_verified
    b=dict(scope='AURA43_ACTIVE_PAPER',market_source='Bitget · USDT-M Futures / api.bitget.com',strategy_version='AURA_4.3_ACTIVE_PAPER_3',
        paper_only=True,exchange_execution=False,read_only=True,state_changed=False,production_paper_verified=False,
        status='BLOCKED',mode='ON',bitget={'status':'CONNECTED'},supabase={'status':'CONNECTED'},
        scheduler={'status':'ERROR','diagnostic_delivery_confirmed':True})
    token='DUMMY_DIAGNOSTIC_ONLY_'+'x'*40;opener=Opener(b);logs=[]
    assert run({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':token},opener=opener,emit=logs.append,diagnose=True)==0
    assert len(opener.requests)==1 and opener.requests[0].full_url==DIAGNOSTIC_URL
    assert token not in ''.join(logs) and '"mode"' not in ''.join(logs)
    assert not diagnostic_verified(body())
    for k,v in [('read_only',False),('state_changed',True),('scheduler',None),('production_paper_verified',True)]:
        assert not diagnostic_verified(dict(b,**{k:v}))


def test_workflow_diagnostic_default_bypasses_only_trading_opt_in():
    from pathlib import Path
    text=Path('.github/workflows/aura-active43.yml').read_text()
    assert 'default: diagnostics' in text and '- diagnostics' in text and '- tick' in text
    assert 'run: python -m scripts.active43_scheduler --diagnose' in text
    assert "default: off_only" in text and "--verify-off-tick" in text
    assert "vars.AURA_ACTIVE43_BITGET_SCHEDULER_ENABLED == 'true'" in text
    assert "inputs.operation == 'diagnostics' || inputs.operation == 'initialize'" in text
    assert '- initialize' in text and 'run: python -m scripts.active43_scheduler --initialize' in text


def test_missing_actions_secret_has_exact_name_and_never_sends_http():
    opener=Opener(body());logs=[]
    assert run({},opener=opener,emit=logs.append,diagnose=True)==1
    assert not opener.requests
    assert any('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET' in line and 'no HTTP request sent' in line for line in logs)


def test_auth_configuration_does_not_emit_secret_length_hash_or_value():
    from scripts.active43_scheduler import auth_configuration
    token='DUMMY_SCHEDULER_SENSITIVE_VALUE_'+'x'*40
    report=auth_configuration({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':' '+token+' '})
    assert report['token_present'] and report['token_has_outer_whitespace']
    encoded=json.dumps(report)
    assert token not in encoded and 'length' not in encoded and 'sha' not in encoded


def test_client_reports_server_auth_code_but_never_raw_error_body():
    import io,urllib.error
    class Reject:
        def open(self,req,timeout):
            assert req.get_method()=='POST'
            assert any(k.lower()=='x-aura-active43-bitget-token' for k,v in req.header_items())
            raise urllib.error.HTTPError(req.full_url,401,'ignored',{},io.BytesIO(json.dumps({'detail':'SCHEDULER_AUTH_REQUIRED','secret':'NEVER_LOG_ME'}).encode()))
    logs=[];token='DUMMY_AUTH_PROBE_'+'x'*40
    assert run({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':token},opener=Reject(),emit=logs.append,diagnose=True)==1
    text='\n'.join(logs)
    assert 'code=SCHEDULER_AUTH_REQUIRED' in text
    assert 'NEVER_LOG_ME' not in text and token not in text
    assert '"header_attached": true' in text and '"origin_header_present": false' in text


def test_diagnostic_codes_explain_database_stage_without_raw_server_data():
    from scripts.active43_scheduler import diagnostic_summary
    report=dict(status='BLOCKED',bitget={'status':'CONNECTED'},supabase={'status':'ERROR',
        'code':'STORAGE_PERMISSION_DENIED','history_rpc_verified':True,'account_read_verified':False,
        'secret':'NEVER_PRINT_THIS'},scheduler={'status':'ERROR','code':'NO_CONFIRMED_TICK'})
    summary=diagnostic_summary(report)
    assert summary['supabase_code']=='STORAGE_PERMISSION_DENIED'
    assert summary['supabase_history_rpc_verified'] and not summary['supabase_account_read_verified']
    assert summary['scheduler_code']=='NO_CONFIRMED_TICK'
    assert 'NEVER_PRINT_THIS' not in json.dumps(summary)
    report['supabase']['code']='NEVER_PRINT_THIS'
    assert diagnostic_summary(report)['supabase_code']=='UNCLASSIFIED_DIAGNOSTIC_ERROR'


def test_guarded_manual_tick_uses_only_existing_off_endpoint_and_confirmation():
    from scripts.active43_scheduler import OFF_TICK_URL,SETUP_CONFIRMATION
    b=dict(body(),mode='OFF',opened=0,processed=False,last_processed_closed_at=None,verification_only=True)
    opener=Opener(b);logs=[];token='DUMMY_MANUAL_OFF_ONLY_'+'x'*40
    assert run({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':token},opener=opener,emit=logs.append,off_tick=True)==0
    assert len(opener.requests)==1
    req=opener.requests[0]
    assert req.full_url==OFF_TICK_URL and req.get_method()=='POST'
    assert json.loads(req.data)=={'confirmation':SETUP_CONFIRMATION}
    assert any('OFF_TICK_VERIFIED' in line for line in logs)
    assert token not in ''.join(logs) and 'production_paper_verified=false' in ''.join(logs)
    for change in ({'verification_only':False},{'mode':'ON'},{'opened':1},{'closed':1},{'state_saved':False}):
        messages=[]
        assert run({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':token},opener=Opener(dict(b,**change)),emit=messages.append,sleep=lambda _:None,off_tick=True)==1
        assert not any('OFF_TICK_VERIFIED' in line for line in messages)


def test_manual_tick_auth_failure_or_on_race_never_falls_back_to_trading_tick():
    import io,urllib.error
    from scripts.active43_scheduler import OFF_TICK_URL
    for status,code in ((401,'SCHEDULER_AUTH_REQUIRED'),(409,'OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT'),(503,'STORAGE_UNAVAILABLE')):
        class Reject:
            def __init__(self):self.urls=[]
            def open(self,req,timeout):
                self.urls.append(req.full_url)
                raise urllib.error.HTTPError(req.full_url,status,'ignored',{},io.BytesIO(json.dumps({'detail':code}).encode()))
        client=Reject();logs=[]
        assert run({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':'DUMMY_'+'x'*40},opener=client,emit=logs.append,sleep=lambda _:None,off_tick=True)==1
        assert client.urls and set(client.urls)=={OFF_TICK_URL}
        assert not any('OFF_TICK_VERIFIED' in line for line in logs)
    opener=Opener(body())
    assert run({},opener=opener,diagnose=True,off_tick=True,emit=lambda _:None)==1
    assert not opener.requests


def test_saved_market_pause_is_reported_once_with_safe_reason_not_unknown_outcome():
    b=dict(body(),status='PAUSED',mode='PAUSED',opened=0,decision='NETWORK_ERROR')
    client=Opener(b);logs=[]
    assert run({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':'DUMMY_'+'x'*40},opener=client,emit=logs.append,sleep=lambda _:None)==1
    assert len(client.requests)==1
    assert any('tick safely blocked:' in line and 'NETWORK_ERROR' in line and '"state_saved": true' in line for line in logs)
    assert not any('outcome unknown' in line for line in logs)
    logs=[]
    assert run({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':'DUMMY_'+'x'*40},opener=Opener(dict(b,decision='SECRET_FROM_UNTRUSTED_RESPONSE')),emit=logs.append)==1
    assert 'UNCLASSIFIED_TICK_REJECTION' in ''.join(logs)
    assert 'SECRET_FROM_UNTRUSTED_RESPONSE' not in ''.join(logs)


def test_corrupt_or_unsaved_pause_cannot_claim_a_saved_safe_rejection():
    for change in ({'state_saved':False},{'scope':'AURA42'},{'exchange_execution':True},{'opened':2}):
        logs=[]
        b=dict(body(),status='PAUSED',mode='PAUSED',opened=0,decision='NETWORK_ERROR');b.update(change)
        assert run({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':'DUMMY_'+'x'*40},opener=Opener(b),emit=logs.append,sleep=lambda _:None)==1
        assert not any('tick safely blocked:' in line for line in logs)
