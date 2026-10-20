"""Opt-in external virtual scheduler. Fixed Render host, separate token, no orders."""
import json,os,time,urllib.request,urllib.error
from scripts.auto42_scheduler import NoRedirect
URL='https://aura-traiding-terminal.onrender.com/api/active43/tick'

SECRET_VARIABLE='AURA_ACTIVE43_BITGET_SCHEDULER_SECRET'
TOKEN_HEADER='X-Aura-Active43-Bitget-Token'
AUTH_CODES={'INITIALIZATION_MARKET_UNVERIFIED','INITIALIZATION_STORAGE_UNVERIFIED','INITIALIZATION_READBACK_FAILED','OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT','OFF_TICK_ACCOUNT_RISK_BLOCKED','SCHEDULER_ACCOUNT_NOT_INITIALIZED','SCHEDULER_NOT_CONFIGURED','SCHEDULER_AUTH_REQUIRED','SCHEDULER_TOKEN_MISSING','SCHEDULER_TOKEN_DUPLICATED','SCHEDULER_TOKEN_MISMATCH','SCHEDULER_ORIGIN_REJECTED','SCHEDULER_SECRET_FORMAT_INVALID'}


def auth_configuration(env):
    token=env.get(SECRET_VARIABLE,'')
    return dict(secret_variable=SECRET_VARIABLE,token_present=bool(token),
        token_format_valid=32<=len(token)<=256 and token.isascii() and token.isprintable(),
        token_has_outer_whitespace=token!=token.strip(),header_name=TOKEN_HEADER,
        diagnostic_endpoint=DIAGNOSTIC_URL,token_source='CURRENT_PROCESS_ENV_NO_FALLBACK')


def rejected_response(exc):
    # Never emit raw headers, body, exception text, token fragments or hashes.
    try:
        raw=exc.read(4097)
        body=json.loads(raw) if len(raw)<=4096 else {}
        detail=body.get('detail',body.get('code')) if type(body) is dict else None
        code=detail.get('code') if type(detail) is dict else detail
        safe=code if type(code) is str and (code in AUTH_CODES or code in DIAGNOSTIC_CODES) else 'UNCLASSIFIED_HTTP_ERROR'
        evidence={}
        if type(detail) is dict and detail.get('component')=='AURA43_SCHEDULER_AUTH':
            evidence['component']='AURA43_SCHEDULER_AUTH'
            for key in ('header_received','origin_rejected'):
                if type(detail.get(key)) is bool:evidence[key]=detail[key]
        return safe+(' evidence='+json.dumps(evidence,sort_keys=True) if evidence else '')
    except (ValueError,OSError):return 'UNCLASSIFIED_HTTP_ERROR'


DIAGNOSTIC_URL='https://aura-traiding-terminal.onrender.com/api/active43/diagnostics/scheduler'


DIAGNOSTIC_CODES=set(('ACTIVE43_DISABLED ACTIVE43_BITGET_DISABLED ACTIVE43_STORAGE_NOT_CONFIGURED '
    'STORAGE_URL_MISSING STORAGE_URL_INVALID STORAGE_KEY_MISSING STORAGE_KEY_INVALID '
    'SCHEDULER_STORAGE_UNVERIFIED SCHEDULER_ACCOUNT_NOT_INITIALIZED '
    'INVALID_STORAGE_CONFIGURATION STORAGE_AUTH STORAGE_PERMISSION_DENIED STORAGE_SCHEMA_MISSING '
    'STORAGE_DATABASE_UNAVAILABLE STORAGE_RATE_LIMIT STORAGE_REDIRECT_BLOCKED STORAGE_HTTP_ERROR '
    'STORAGE_RESPONSE_LIMIT STORAGE_INVALID_RESPONSE STORAGE_UNAVAILABLE STORAGE_UNAVAILABLE_OUTCOME_UNKNOWN '
    'STORAGE_TIMEOUT_OUTCOME_UNKNOWN STORAGE_READ_TIMEOUT CORRUPT_PORTFOLIO '
    'ACTIVE_SCOPE_OR_CONFIG_MISMATCH STORAGE_SCOPE_MISMATCH CONFIG_CHANGED DIAGNOSTIC_TIMEOUT '
    'SCHEDULER_NOT_CONFIGURED NO_CONFIRMED_TICK STALE_TICK REGION_OR_ACCESS_RESTRICTED '
    'RATE_LIMIT UPSTREAM_TIMEOUT NETWORK_ERROR HTTP_ERROR UPSTREAM_API_ERROR '
    'UPSTREAM_CLOCK_OR_STALE_RESPONSE SOURCE_MISMATCH STALE_OR_MISMATCHED_DATA '
    'FUTURES_FILTERS_UNAVAILABLE FUTURES_FILTERS_CHANGED NOT_INITIALIZED').split())


def diagnostic_summary(body):
    def code(section):
        value=body[section].get('code')
        return value if type(value) is str and value in DIAGNOSTIC_CODES else None if value is None else 'UNCLASSIFIED_DIAGNOSTIC_ERROR'
    db=body['supabase']
    config=body.get('configuration') if type(body.get('configuration')) is dict else {}
    storage=config.get('storage') if type(config.get('storage')) is dict else {}
    def flag(mapping,key):return mapping.get(key) if type(mapping.get(key)) is bool else None
    missing=config.get('missing_variables') if type(config.get('missing_variables')) is list else []
    return dict(status=body['status'],bitget=body['bitget']['status'],bitget_code=code('bitget'),
        supabase=db['status'],supabase_code=code('supabase'),
        supabase_stage=db.get('stage') if db.get('stage') in ('CONFIGURATION','HISTORY_RPC','ACCOUNT_READ','STATE_VALIDATION','COMPLETE') else None,
        supabase_history_rpc_verified=db.get('history_rpc_verified') is True,
        supabase_account_read_verified=db.get('account_read_verified') is True,
        supabase_account_status='NOT_INITIALIZED' if db.get('account_status')=='NOT_INITIALIZED' else None,
        scheduler=body['scheduler']['status'],scheduler_code=code('scheduler'),
        server_module_enabled=flag(config,'server_enabled'),
        storage_url_format_valid=flag(storage,'url_format_valid'),storage_key_format_valid=flag(storage,'key_format_valid'),
        storage_url_padding_normalized=flag(storage,'url_padding_normalized'),storage_key_padding_normalized=flag(storage,'key_padding_normalized'),
        storage_missing_variables=[name for name in missing if name in ('AURA_ACTIVE43_BITGET_SUPABASE_URL','AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY')],
        state_changed=False,production_paper_verified=False)


def diagnostic_verified(body):
    return (type(body) is dict and body.get('scope')=='AURA43_ACTIVE_PAPER'
        and body.get('market_source')=='Bitget · USDT-M Futures / api.bitget.com'
        and body.get('strategy_version')=='AURA_4.3_ACTIVE_PAPER_3'
        and body.get('paper_only') is True and body.get('exchange_execution') is False
        and body.get('read_only') is True and body.get('state_changed') is False
        and body.get('production_paper_verified') is False
        and type(body.get('scheduler')) is dict and body['scheduler'].get('diagnostic_delivery_confirmed') is True
        and body.get('status') in ('PASS','BLOCKED')
        and all(type(body.get(k)) is dict and body[k].get('status') in ('CONNECTED','ACTIVE','ERROR') for k in ('bitget','supabase','scheduler')))


def verified(body):
    if (type(body) is not dict or body.get('paper_only') is not True or body.get('exchange_execution') is not False
        or body.get('scope')!='AURA43_ACTIVE_PAPER' or body.get('market_source')!='Bitget · USDT-M Futures / api.bitget.com'
        or body.get('strategy_version')!='AURA_4.3_ACTIVE_PAPER_3' or body.get('state_saved') is not True
        or body.get('status')!='COMPLETED' or body.get('mode') not in ('ON','OFF','PAUSED','EMERGENCY')
        or type(body.get('processed')) is not bool or type(body.get('duplicate')) is not bool
        or any(type(body.get(k)) is not int or not 0<=body[k]<=1 for k in ('opened','closed'))):return False
    at=body.get('last_processed_closed_at')
    return at is None and not body['processed'] or type(at) is int and at>=0 and at%300==0


def run(env=None,opener=None,sleep=time.sleep,emit=print,diagnose=False):
    env=os.environ if env is None else env;token=env.get(SECRET_VARIABLE,'')
    if diagnose:emit('ACTIVE43 client auth configuration: '+json.dumps(auth_configuration(env),sort_keys=True))
    if not token:
        emit('ACTIVE43: SCHEDULER_NOT_CONFIGURED; missing Actions secret AURA_ACTIVE43_BITGET_SCHEDULER_SECRET; no HTTP request sent');return 1
    if not 32<=len(token)<=256 or not token.isascii() or not token.isprintable():emit('ACTIVE43: SCHEDULER_NOT_CONFIGURED');return 1
    client=opener or urllib.request.build_opener(NoRedirect)
    for attempt in range(3):
        try:
            req=urllib.request.Request(DIAGNOSTIC_URL if diagnose else URL,data=b'',method='POST',headers={TOKEN_HEADER:token})
            if diagnose:emit('ACTIVE43 request auth: '+json.dumps(dict(header_attached=any(k.lower()==TOKEN_HEADER.lower() for k,v in req.header_items()),origin_header_present=req.has_header('Origin'),method=req.get_method())))
            with client.open(req,timeout=90) as r:
                raw=r.read(65537)
                if r.status!=200 or len(raw)>65536:raise ValueError()
                body=json.loads(raw)
                if diagnose:
                    if not diagnostic_verified(body):raise ValueError()
                    # Whitelist booleans/status only: no raw responses, env or exceptions.
                    emit('ACTIVE43 read-only diagnostic delivery confirmed: '+json.dumps(diagnostic_summary(body),sort_keys=True))
                    return 0 if body['bitget']['status']=='CONNECTED' and body['supabase']['status']=='CONNECTED' else 1
                if not verified(body):raise ValueError()
                emit('ACTIVE43 tick confirmed: '+json.dumps({k:body[k] for k in ('mode','processed','duplicate','opened','closed')}));return 0
        except urllib.error.HTTPError as exc:
            emit('ACTIVE43 request rejected: HTTP '+str(exc.code)+' code='+rejected_response(exc))
            if exc.code in (301,302,303,307,308,401,403,404):return 1
        except (OSError,ValueError,TypeError):emit('ACTIVE43 request not confirmed; outcome unknown')
        if attempt<2:sleep(2**(attempt+1))
    return 1


INITIALIZE_URL='https://aura-traiding-terminal.onrender.com/api/active43/initialize'
OFF_TICK_URL='https://aura-traiding-terminal.onrender.com/api/active43/verify-off-tick'
SETUP_CONFIRMATION='INITIALIZE ISOLATED PAPER ACCOUNT'


def initialization_verified(body):
    return (type(body) is dict and body.get('operation')=='INITIALIZE_PAPER_ACCOUNT' and body.get('status')=='ACCOUNT_AVAILABLE'
        and body.get('scope')=='AURA43_ACTIVE_PAPER' and body.get('market_source')=='Bitget · USDT-M Futures / api.bitget.com'
        and body.get('strategy_version')=='AURA_4.3_ACTIVE_PAPER_3'
        and all(body.get(k) is True for k in ('paper_only','account_available','state_saved','readback_verified','existing_account_preserved'))
        and all(body.get(k) is False for k in ('exchange_execution','mode_changed_by_operation','trade_execution_performed','production_paper_verified'))
        and body.get('mode') in ('ON','OFF','PAUSED','EMERGENCY')
        and type(body.get('position_present')) is bool and type(body.get('initial_balance_matches')) is bool)


def prepare(env=None,opener=None,emit=print):
    """Explicit setup only; never calls unrestricted tick/control or creates signals."""
    env=os.environ if env is None else env;token=env.get(SECRET_VARIABLE,'')
    if not 32<=len(token)<=256 or not token.isascii() or not token.isprintable():
        emit('ACTIVE43 setup: SCHEDULER_NOT_CONFIGURED');return 1
    client=opener or urllib.request.build_opener(NoRedirect)
    def request(url,confirmed=False):
        payload=json.dumps({'confirmation':SETUP_CONFIRMATION}).encode() if confirmed else b''
        req=urllib.request.Request(url,data=payload,method='POST',headers={TOKEN_HEADER:token,'Content-Type':'application/json'})
        with client.open(req,timeout=90) as r:
            raw=r.read(65537)
            if r.status!=200 or len(raw)>65536:raise ValueError()
            return json.loads(raw)
    phase='PREFLIGHT'
    try:
        before=request(DIAGNOSTIC_URL)
        if not diagnostic_verified(before) or any(before[k]['status']!='CONNECTED' for k in ('bitget','supabase')):
            emit('ACTIVE43 setup: PREFLIGHT_UNVERIFIED');return 1
        emit('ACTIVE43 setup preflight: '+json.dumps(diagnostic_summary(before),sort_keys=True))
        configuration=before.get('configuration') if type(before.get('configuration')) is dict else {}
        if configuration.get('server_enabled') is not True:
            emit('ACTIVE43 setup: SERVER_MODULE_DISABLED');return 1
        phase='INITIALIZE'
        account=request(INITIALIZE_URL,True)
        if not initialization_verified(account):raise ValueError()
        if account['mode']!='OFF' or account['position_present']:
            emit('ACTIVE43 setup: EXISTING_ACCOUNT_PRESERVED_NOT_EMPTY_OFF; no heartbeat or trading performed');return 1
        phase='OFF_HEARTBEAT'
        heartbeat=request(OFF_TICK_URL,True)
        if not verified(heartbeat) or heartbeat.get('verification_only') is not True or heartbeat['mode']!='OFF' or heartbeat['opened']!=0 or heartbeat['closed']!=0:
            raise ValueError()
        phase='POSTFLIGHT'
        after=request(DIAGNOSTIC_URL)
        if not diagnostic_verified(after):raise ValueError()
        emit('ACTIVE43 prepared account diagnostic: '+json.dumps(diagnostic_summary(after),sort_keys=True))
        if after['status']!='PASS' or after['scheduler']['status']!='ACTIVE' or after.get('mode')!='OFF':
            emit('ACTIVE43 setup: POSTFLIGHT_UNVERIFIED');return 1
        emit('ACTIVE43 PREPARATION_VERIFIED: '+json.dumps(dict(account_available=True,readback_verified=True,
            off_scheduler_tick_saved=True,initial_balance_matches=account['initial_balance_matches'],
            auto_paper_enabled=False,production_paper_verified=False)))
        return 0
    except urllib.error.HTTPError as exc:
        code='SETUP_API_NOT_DEPLOYED' if exc.code==404 and phase in ('INITIALIZE','OFF_HEARTBEAT') else rejected_response(exc)
        emit('ACTIVE43 setup rejected: phase='+phase+' HTTP '+str(exc.code)+' code='+code);return 1
    except (OSError,ValueError,TypeError):
        emit('ACTIVE43 setup unconfirmed; no trading retry; rerun setup safely');return 1


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_mutually_exclusive_group()
    actions.add_argument('--diagnose',action='store_true',help='read-only probes, no scheduler tick or portfolio writes')
    actions.add_argument('--initialize',action='store_true',help='explicit isolated account setup and guarded OFF heartbeat; never enables trading')
    args=parser.parse_args()
    raise SystemExit(prepare() if args.initialize else run(diagnose=args.diagnose))
