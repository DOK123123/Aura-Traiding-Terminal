"""TEST ONLY: existing production controller and isolated SQLite, never live data."""
import argparse
import asyncio
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from app.automated.service import Service
from app.automated.storage import SQLiteStore
from app.automated.live_evidence import code_hashes
from app.lab.models import canonical,digest
from scripts.verify_auto42_execution import TestMarket,seed_store,run as verify_execution


async def monitor_trace() -> dict:
    market=TestMarket('LONG');now=[market.bars[-1].time+930]
    with tempfile.TemporaryDirectory(prefix='aura-monitor-test-only-') as folder:
        path=Path(folder)/'auto-paper-42.sqlite3';store=await seed_store(path,now,'TEST_ONLY_MONITOR')
        svc=Service(market,store,clock=lambda:now[0])
        try:
            with patch('app.automated.service.scheduler_configured',return_value=True):await svc.control('START','a'*32)
            market.add();now[0]+=900;await svc.tick()
            market.add();now[0]+=900;await asyncio.gather(svc.tick(),svc.tick())
            opened=await svc.live_monitor();position=opened['position']
            assert position and opened['status']=='WAITING_FOR_REAL_SIGNAL'
            assert opened['last_open']['signal']['event_type']=='SIGNAL'
            await svc.close()
            store=SQLiteStore(path,clock=lambda:now[0]);svc=Service(market,store,clock=lambda:now[0])
            restored=await svc.live_monitor();assert restored['position']==position
            before=await store.load();await svc.live_monitor();assert before==await store.load()
            # Intermediate observation uses the same closed-candle liquidation mark.
            market.signal=False;market.add();now[0]+=900;await svc.tick()
            market.add(h=str(D(position['take_profit'])+1));now[0]+=900;await svc.tick()
            result=await svc.live_monitor();assert result['position'] is None
            assert result['last_close']['event_type']=='CLOSE_TP' and not result['live_cycle_verified']
            rows=await store.history(limit=200);monitor=[e['payload'] for e in rows if e['kind']=='LIVE_MONITOR']
            assert sum(e['event_type']=='OPEN' for e in monitor)==1
            assert sum(e['event_type']=='CLOSE_TP' for e in monitor)==1
            assert any(e['event_type']=='POSITION_UPDATE' for e in monitor)
            assert all(e['scheduler_run_id'] and e['candle_id'] and e['source'] for e in monitor)
            return dict(status='PASS',test_only=True,opened=1,closed=1,restart_restored=True,
                duplicate_prevented=True,read_only_verified=True,event_types=sorted({e['event_type'] for e in monitor}),
                monitor_status=result['status'],live_cycle_verified=False,balance=result['balance'],
                fees=result['fees'],realized_pnl=result['realized_pnl'])
        finally:await svc.close()


async def run() -> dict:
    if not __debug__:raise RuntimeError('VERIFICATION_REQUIRES_ASSERTIONS')
    with patch.dict('os.environ',RENDER='',RENDER_GIT_COMMIT=''):
        accounting=await verify_execution();trace=await monitor_trace()
    return dict(status='PASS',test_only=True,evidence_type='ISOLATED_TEMPORARY_SQLITE_NOT_PRODUCTION',
        code_hashes=code_hashes(),accounting=accounting,monitor_trace=trace,proves_live_autonomy=False,
        supabase_live='NOT_TESTED',render_live='NOT_TESTED')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sandbox-poll',action='store_true');args=p.parse_args()
    if args.sandbox_poll:
        from scripts.replay_aura_csv import enable_sandbox_poll
        enable_sandbox_poll()
    value=asyncio.run(run());value['checksum']=digest(value);args.output.write_bytes(canonical(value))
    print(json.dumps(dict(status=value['status'],test_only=True,monitor_trace=value['monitor_trace'])))


if __name__=='__main__':main()
