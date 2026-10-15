"""Bounded authenticated scheduler client. Standard library; no exchange calls."""
import json,os,socket,ssl,time,urllib.error,urllib.parse,urllib.request,http.client

HOST='aura-traiding-terminal.onrender.com'
PATH='/api/auto42/tick'
TIMEOUT=120
SAFE_CODES=set('SCHEDULER_NOT_CONFIGURED SCHEDULER_AUTH_REQUIRED STORAGE_NOT_CONFIGURED STORAGE_AUTH STORAGE_PERMISSION_DENIED STORAGE_SCHEMA_MISSING STORAGE_DATABASE_UNAVAILABLE STORAGE_RATE_LIMIT STORAGE_HTTP_ERROR STORAGE_REDIRECT_BLOCKED STORAGE_DNS STORAGE_TLS STORAGE_CONNECT STORAGE_PROXY STORAGE_READ STORAGE_WRITE STORAGE_PROTOCOL STORAGE_NETWORK STORAGE_TIMEOUT STORAGE_INVALID_RESPONSE CORRUPT_PORTFOLIO CONCURRENT_UPDATE TICK_TIMEOUT REQUEST_TIMEOUT STALE_DATA SNAPSHOT_MISMATCH MTF_UNAVAILABLE INVALID_ANALYSIS MISSING_CANDLES SOURCE_CORRECTION_OR_HISTORY_MISSING CATCHUP_LIMIT DAILY_LOSS_LIMIT DRAWDOWN_LIMIT EMERGENCY_STOP AUTO_OFF OWNER_STOP ACTIVATION_BASELINE NO_CONFIRMED_SETUP SIGNAL_QUEUED_NEXT_OPEN POSITION_ALREADY_OPEN MTF_NOT_ALIGNED TREND_NOT_ALIGNED TREND_TOO_WEAK REGIME_FILTER OPPOSING_LIQUIDITY NO_CONFIRMED_STRUCTURE_BREAK VOLATILITY_FILTER INVALID_STOPS OPPOSING_LEVEL_TOO_CLOSE CONFIRMED_STRUCTURE_RETEST'.split())
SAFE_CODES.update({'NETWORK_ERROR','RATE_LIMIT','REGION_RESTRICTED','UPSTREAM_HTTP_ERROR','INVALID_DATA',
    'INVALID_TIMESTAMPS','DUPLICATE_OR_UNORDERED','INVALID_CLOSE_TIME','INVALID_OHLCV',
    'DATA_LIMIT','INSUFFICIENT_HISTORY','PUBLIC_DATA_UNAVAILABLE','UNAVAILABLE',
    'UPSTREAM_TIMEOUT','ANALYSIS_TIMEOUT'})
OUTCOMES={'HEARTBEAT_OFF','NO_NEW_CANDLE','NO_NEW_WORK','CANDLE_PROCESSED','DATA_BLOCKED','RISK_BLOCKED'}


class SchedulerError(Exception):
    def __init__(self,code,http_status=None,retryable=False):self.code=code;self.http_status=http_status;self.retryable=retryable;super().__init__(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def configuration(env):
    url=env.get('AURA_AUTO42_TICK_URL',env.get('TICK_URL',''));token=env.get('AURA_AUTO42_SCHEDULER_SECRET',env.get('TOKEN',''))
    if not url:raise SchedulerError('CONFIG_URL_MISSING')
    if url!=url.strip():raise SchedulerError('CONFIG_URL_WHITESPACE')
    try:
        u=urllib.parse.urlsplit(url)
        if u.scheme!='https':raise SchedulerError('CONFIG_URL_SCHEME')
        if u.hostname!=HOST:raise SchedulerError('CONFIG_URL_HOST')
        if u.port is not None or u.username or u.password:raise SchedulerError('CONFIG_URL_AUTHORITY')
        if u.path!=PATH or u.query or u.fragment:raise SchedulerError('CONFIG_URL_PATH')
    except ValueError:raise SchedulerError('CONFIG_URL_INVALID') from None
    if not token:raise SchedulerError('CONFIG_TOKEN_MISSING')
    if not 32<=len(token)<=256 or not token.isascii() or not token.isprintable():raise SchedulerError('CONFIG_TOKEN_FORMAT')
    return url,token


def safe_code(value):return value if isinstance(value,str) and value in SAFE_CODES else 'UNCLASSIFIED_SERVER_ERROR'


def decode(raw):
    try:return json.loads(raw)
    except (ValueError,UnicodeError):raise SchedulerError('API_INVALID_JSON') from None


def verified_result(body):
    if not isinstance(body,dict):raise SchedulerError('API_INVALID_JSON')
    if body.get('paper_only') is not True or body.get('exchange_execution') is not False:raise SchedulerError('API_SAFETY_BOUNDARY')
    if body.get('status')!='COMPLETED':raise SchedulerError(safe_code(body.get('code') or body.get('decision')))
    if (body.get('state_saved') is not True or type(body.get('processed_this_run')) is not bool or
        body.get('tick_outcome') not in OUTCOMES or body.get('mode') not in ('ON','OFF','PAUSED','EMERGENCY','ERROR')):raise SchedulerError('API_CONTRACT_MISMATCH')
    if body['tick_outcome']=='CANDLE_PROCESSED' and body['processed_this_run'] is not True:raise SchedulerError('API_CONTRACT_MISMATCH')
    if body['processed_this_run']:
        at=body.get('last_processed_closed_at')
        if body['tick_outcome'] not in ('CANDLE_PROCESSED','RISK_BLOCKED') or type(at) is not int or at%900:raise SchedulerError('API_CONTRACT_MISMATCH')
    for key in ('opened_positions','closed_positions'):
        if type(body.get(key)) is not int or not 0<=body[key]<=1:raise SchedulerError('API_CONTRACT_MISMATCH')
    return dict(outcome=body['tick_outcome'],mode=body['mode'],decision=safe_code(body.get('decision')),
        processed=body['processed_this_run'],opened=body['opened_positions'],closed=body['closed_positions'])


def run(env=None,opener=None,sleep=time.sleep,emit=print):
    try:url,token=configuration(os.environ if env is None else env)
    except SchedulerError as exc:emit('Auto42 configuration: code='+exc.code);return 1
    client=opener or urllib.request.build_opener(NoRedirect)
    for attempt in range(3):
        try:
            request=urllib.request.Request(url,data=b'',method='POST',headers={'X-Aura-Auto42-Token':token})
            with client.open(request,timeout=TIMEOUT) as response:
                raw=response.read(65537)
                if len(raw)>65536:raise SchedulerError('API_RESPONSE_LIMIT',response.status)
                if response.status!=200:raise SchedulerError('HTTP_ERROR',response.status)
                result=verified_result(decode(raw))
            emit('Auto42 verified: outcome={outcome} mode={mode} decision={decision} processed={processed} opened={opened} closed={closed}'.format(**result))
            return 0
        except urllib.error.HTTPError as exc:
            try:body=decode(exc.read(65536));code=safe_code(body.get('code') or body.get('detail')) if isinstance(body,dict) else 'HTTP_ERROR'
            except SchedulerError:code='HTTP_NON_JSON'
            fatal=exc.code in (301,302,303,307,308,401,403,404) or code in {'STORAGE_AUTH','STORAGE_SCHEMA_MISSING','STORAGE_PERMISSION_DENIED','SCHEDULER_NOT_CONFIGURED'}
            error=SchedulerError(code,exc.code,retryable=not fatal and exc.code in (408,409,429,500,502,503,504))
        except (TimeoutError,socket.timeout):error=SchedulerError('RENDER_OR_BACKEND_TIMEOUT',retryable=True)
        except urllib.error.URLError as exc:
            reason=exc.reason
            code='RENDER_OR_BACKEND_TIMEOUT' if isinstance(reason,(TimeoutError,socket.timeout)) else 'CLIENT_DNS' if isinstance(reason,socket.gaierror) else 'CLIENT_TLS' if isinstance(reason,ssl.SSLError) else 'CLIENT_NETWORK'
            error=SchedulerError(code,retryable=code!='CLIENT_TLS')
        except SchedulerError as exc:error=exc
        except (OSError,http.client.HTTPException):error=SchedulerError('CLIENT_NETWORK',retryable=True)
        except (ValueError,TypeError):error=SchedulerError('CLIENT_PROTOCOL_ERROR')
        emit('Auto42 attempt={}/3 http={} code={}'.format(attempt+1,error.http_status if error.http_status is not None else 'NONE',error.code))
        if not error.retryable or attempt==2:return 1
        sleep(2**(attempt+1))
    return 1


if __name__=='__main__':raise SystemExit(run())
