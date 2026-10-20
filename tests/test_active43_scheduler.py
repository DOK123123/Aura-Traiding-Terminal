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
    assert "if: github.event_name == 'schedule' || inputs.operation == 'tick'" in text
    assert "vars.AURA_ACTIVE43_BITGET_SCHEDULER_ENABLED == 'true'" in text
    assert "(github.event_name == 'workflow_dispatch' && inputs.operation == 'diagnostics') ||" in text


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
