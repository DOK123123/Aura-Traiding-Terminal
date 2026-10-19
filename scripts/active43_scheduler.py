"""Opt-in external virtual scheduler. Fixed Render host, separate token, no orders."""
import json,os,time,urllib.request,urllib.error
from scripts.auto42_scheduler import NoRedirect
URL='https://aura-traiding-terminal.onrender.com/api/active43/tick'

DIAGNOSTIC_URL='https://aura-traiding-terminal.onrender.com/api/active43/diagnostics/scheduler'


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
    env=os.environ if env is None else env;token=env.get('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET','')
    if not 32<=len(token)<=256 or not token.isascii() or not token.isprintable():emit('ACTIVE43: SCHEDULER_NOT_CONFIGURED');return 1
    client=opener or urllib.request.build_opener(NoRedirect)
    for attempt in range(3):
        try:
            req=urllib.request.Request(DIAGNOSTIC_URL if diagnose else URL,data=b'',method='POST',headers={'X-Aura-Active43-Bitget-Token':token})
            with client.open(req,timeout=90) as r:
                raw=r.read(65537)
                if r.status!=200 or len(raw)>65536:raise ValueError()
                body=json.loads(raw)
                if diagnose:
                    if not diagnostic_verified(body):raise ValueError()
                    # Whitelist booleans/status only: no raw responses, env or exceptions.
                    emit('ACTIVE43 read-only diagnostic delivery confirmed: '+json.dumps({
                        'status':body['status'], 'bitget':body['bitget']['status'],
                        'supabase':body['supabase']['status'], 'scheduler':body['scheduler']['status'],
                        'state_changed':False, 'production_paper_verified':False}))
                    return 0 if body['bitget']['status']=='CONNECTED' and body['supabase']['status']=='CONNECTED' else 1
                if not verified(body):raise ValueError()
                emit('ACTIVE43 tick confirmed: '+json.dumps({k:body[k] for k in ('mode','processed','duplicate','opened','closed')}));return 0
        except urllib.error.HTTPError as exc:
            emit('ACTIVE43 request rejected: HTTP '+str(exc.code))
            if exc.code in (301,302,303,307,308,401,403,404):return 1
        except (OSError,ValueError,TypeError):emit('ACTIVE43 request not confirmed; outcome unknown')
        if attempt<2:sleep(2**(attempt+1))
    return 1

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnose',action='store_true',help='read-only probes, no scheduler tick or portfolio writes')
    raise SystemExit(run(diagnose=parser.parse_args().diagnose))
