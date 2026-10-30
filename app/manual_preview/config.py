"""Fail-closed preview configuration. No production credential fallback."""
import base64
from dataclasses import dataclass,field
import json
import re
import time

# Public identity from existing repository documentation, never a credential.
PRODUCTION_REFS=frozenset({'uvcbhicbnqpqobxnufph'})

@dataclass(frozen=True)
class Config:
    owner_password:str=field(repr=False)
    project_ref:str
    url:str
    key:str=field(repr=False)
    manual_enabled:bool=False
    signals_enabled:bool=False


def parse(env,clock=time.time):
    if (env.get('RENDER_SERVICE_ID')=='srv-db5tonlckfvc73be2m5g' or env.get('RENDER_EXTERNAL_HOSTNAME')=='aura-traiding-terminal.onrender.com'):
        raise ValueError('PREVIEW_PRODUCTION_SERVICE_FORBIDDEN')
    if env.get('AURA_PREVIEW_ONLY')!='true':raise ValueError('PREVIEW_MODE_REQUIRED')
    for name in env:
        if (name.startswith('AURA_') and not name.startswith('AURA_PREVIEW_')
                or name.startswith(('SUPABASE_','BYBIT_','BINANCE_','BITGET_','CLOUDFLARE_','CF_'))
                or name in {'DATABASE_URL','PGPASSWORD','PGSERVICE','RENDER_API_KEY','RENDER_DEPLOY_HOOK','GITHUB_TOKEN','GH_TOKEN'}):
            raise ValueError('PREVIEW_FOREIGN_ENV_FORBIDDEN')
    password=env.get('AURA_PREVIEW_OWNER_PASSWORD','')
    if not 16<=len(password)<=256 or not password.isascii() or not password.isprintable():raise ValueError('PREVIEW_OWNER_PASSWORD_REQUIRED')
    ref=env.get('AURA_PREVIEW_PROJECT_REF','')
    if not re.fullmatch('[a-z0-9]{20}',ref) or ref in PRODUCTION_REFS:raise ValueError('PREVIEW_PROJECT_FORBIDDEN')
    url=env.get('AURA_PREVIEW_SUPABASE_URL','')
    if url!='https://'+ref+'.supabase.co':raise ValueError('PREVIEW_PROJECT_URL_MISMATCH')
    key=env.get('AURA_PREVIEW_SUPABASE_SERVICE_KEY','')
    # Modern secret keys are verified by the pinned host and read-only DB guard.
    # A foreign key fails authentication there before any ledger RPC is sent.
    if key.startswith('sb_secret_'):
        if not re.fullmatch(r'sb_secret_[A-Za-z0-9_-]{24,200}',key):raise ValueError('PREVIEW_PROJECT_BOUND_KEY_REQUIRED')
    else:
      try:
        parts=key.split('.')
        if len(parts)!=3 or not 32<=len(key)<=8192 or any(not re.fullmatch('[A-Za-z0-9_-]+',p) for p in parts):raise ValueError()
        claims=json.loads(base64.urlsafe_b64decode(parts[1]+'='*(-len(parts[1])%4)))
        if (claims.get('role')!='service_role' or claims.get('ref')!=ref
                or type(claims.get('exp')) is not int or claims['exp']<=clock()):raise ValueError()
      except (ValueError,TypeError,KeyError,AttributeError,UnicodeError):
        raise ValueError('PREVIEW_PROJECT_BOUND_KEY_REQUIRED') from None
    # Parsing above is a deny guard, NOT signature verification/authentication.
    # The dedicated Supabase host still verifies the JWT signature and role.
    enabled=env.get('AURA_PREVIEW_MANUAL_ENABLED','false')
    if enabled not in ('true','false'):raise ValueError('PREVIEW_MANUAL_FLAG_INVALID')
    signals=env.get('AURA_PREVIEW_SIGNALS_ENABLED','false')
    if signals not in ('true','false'):raise ValueError('PREVIEW_SIGNALS_FLAG_INVALID')
    return Config(password,ref,url,key,enabled=='true',signals=='true')
