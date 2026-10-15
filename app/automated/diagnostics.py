"""Whitelisted operational evidence; never URLs, keys or raw exception text."""
import os,socket,ssl,time
from urllib.parse import urlsplit
import re
import httpx

URL_ENV='AURA_AUTO42_SUPABASE_URL'
KEY_ENV='AURA_AUTO42_SUPABASE_SERVICE_KEY'
UPSTREAM_CODES={'42P01','42501','42883','23505','PGRST000','PGRST001','PGRST002','PGRST202','PGRST205','PGRST301','PGRST302'}


def configuration():
    url=os.getenv(URL_ENV,'');key=os.getenv(KEY_ENV,'');local=os.getenv('AURA_AUTO42_SQLITE_PATH','')
    missing=[];invalid=[]
    if not local:
        if not url:missing.append(URL_ENV)
        elif not re.fullmatch(r'https://[a-z0-9]{12,40}\.supabase\.co',url):invalid.append(URL_ENV)
        if not key:missing.append(KEY_ENV)
        elif not 32<=len(key)<=8192 or not key.isascii() or not key.isprintable():invalid.append(KEY_ENV)
    if local and (url or key):invalid.append('AURA_AUTO42_SQLITE_PATH')
    if local and os.getenv('RENDER','').lower() in ('1','true'):invalid.append('AURA_AUTO42_SQLITE_PATH')
    return dict(missing_variables=missing,invalid_variables=sorted(set(invalid)),
        scheduler_secret_present=bool(os.getenv('AURA_AUTO42_SCHEDULER_SECRET','')),
        ignored_generic_variables=[name for name in ('SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','SUPABASE_SERVICE_KEY') if os.getenv(name)])


def network_kind(exc):
    # Inspect exception classes/causes, not messages containing signed data.
    queue=[exc];seen=set();chain=[]
    while queue and len(chain)<20:
        x=queue.pop()
        if id(x) in seen:continue
        seen.add(id(x));chain.append(x)
        for cause in (getattr(x,'__cause__',None),getattr(x,'__context__',None)):
            if cause is not None:queue.append(cause)
    if any(isinstance(x,socket.gaierror) for x in chain):return 'DNS'
    if any(isinstance(x,ssl.SSLError) for x in chain):return 'TLS'
    if isinstance(exc,httpx.ProxyError):return 'PROXY'
    if isinstance(exc,httpx.ConnectError):return 'CONNECT'
    if isinstance(exc,httpx.ReadError):return 'READ'
    if isinstance(exc,httpx.WriteError):return 'WRITE'
    if isinstance(exc,httpx.ProtocolError):return 'PROTOCOL'
    return 'NETWORK'


def http_error(status,body):
    upstream=body.get('code') if isinstance(body,dict) else None
    if not isinstance(upstream,str) or upstream not in UPSTREAM_CODES:upstream=None
    if upstream in {'42P01','42883','PGRST202','PGRST205'}:code='STORAGE_SCHEMA_MISSING'
    elif upstream=='42501':code='STORAGE_PERMISSION_DENIED'
    elif upstream in {'PGRST000','PGRST001','PGRST002'}:code='STORAGE_DATABASE_UNAVAILABLE'
    elif status in (401,403):code='STORAGE_AUTH'
    elif status==429:code='STORAGE_RATE_LIMIT'
    elif 300<=status<400:code='STORAGE_REDIRECT_BLOCKED'
    else:code='STORAGE_HTTP_ERROR'
    return code,upstream


def error_category(code):
    """Stable categories for owner diagnosis, retaining the specific error code."""
    if not code:return None
    if code=='STORAGE_DNS':return 'DNS_ERROR'
    if code in {'STORAGE_AUTH','STORAGE_PERMISSION_DENIED'}:return 'AUTH_ERROR'
    if code=='STORAGE_SCHEMA_MISSING':return 'SCHEMA_ERROR'
    if code in {'STORAGE_NOT_CONFIGURED','INVALID_STORAGE_CONFIGURATION','AMBIGUOUS_STORAGE','RENDER_REQUIRES_DURABLE_STORAGE'}:return 'CONFIG_ERROR'
    if code in {'STORAGE_DATABASE_UNAVAILABLE','CORRUPT_PORTFOLIO','STORAGE_INVALID_RESPONSE'}:return 'DATABASE_ERROR'
    if code in {'STORAGE_NETWORK','STORAGE_CONNECT','STORAGE_READ','STORAGE_WRITE','STORAGE_PROTOCOL','STORAGE_PROXY','STORAGE_TLS','STORAGE_TIMEOUT'}:return 'NETWORK_ERROR'
    return 'STORAGE_ERROR'


def connection_evidence(store):
    """Only validated public host from the instantiated client, never raw env/URL."""
    base=getattr(getattr(store,'transport',None),'base',None)
    host=urlsplit(base).hostname if isinstance(base,str) and re.fullmatch(r'https://[a-z0-9]{12,40}\.supabase\.co',base) else None
    return dict(hostname=host,url_variable=URL_ENV,protocol='HTTPS_REST_RPC' if host else None)
