"""Opt-in external virtual scheduler. Fixed Render host, separate token, no orders."""
import json,os,time,urllib.request,urllib.error
from scripts.auto42_scheduler import NoRedirect
URL='https://aura-traiding-terminal.onrender.com/api/active43/tick'


def verified(body):
    if (type(body) is not dict or body.get('paper_only') is not True or body.get('exchange_execution') is not False
        or body.get('scope')!='AURA43_ACTIVE_PAPER' or body.get('state_saved') is not True
        or body.get('status')!='COMPLETED' or body.get('mode') not in ('ON','OFF','PAUSED','EMERGENCY')
        or type(body.get('processed')) is not bool or type(body.get('duplicate')) is not bool
        or any(type(body.get(k)) is not int or not 0<=body[k]<=1 for k in ('opened','closed'))):return False
    at=body.get('last_processed_closed_at')
    return at is None and not body['processed'] or type(at) is int and at>=0 and at%300==0


def run(env=None,opener=None,sleep=time.sleep,emit=print):
    env=os.environ if env is None else env;token=env.get('AURA_ACTIVE43_SCHEDULER_SECRET','')
    if not 32<=len(token)<=256 or not token.isascii() or not token.isprintable():emit('ACTIVE43: SCHEDULER_NOT_CONFIGURED');return 1
    client=opener or urllib.request.build_opener(NoRedirect)
    for attempt in range(3):
        try:
            req=urllib.request.Request(URL,data=b'',method='POST',headers={'X-Aura-Active43-Token':token})
            with client.open(req,timeout=90) as r:
                raw=r.read(65537)
                if r.status!=200 or len(raw)>65536:raise ValueError()
                body=json.loads(raw)
                if not verified(body):raise ValueError()
                emit('ACTIVE43 tick confirmed: '+json.dumps({k:body[k] for k in ('mode','processed','duplicate','opened','closed')}));return 0
        except urllib.error.HTTPError as exc:
            emit('ACTIVE43 request rejected: HTTP '+str(exc.code))
            if exc.code in (301,302,303,307,308,401,403,404):return 1
        except (OSError,ValueError,TypeError):emit('ACTIVE43 request not confirmed; outcome unknown')
        if attempt<2:sleep(2**(attempt+1))
    return 1

if __name__=='__main__':raise SystemExit(run())
