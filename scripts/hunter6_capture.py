"""One bounded public-market cycle; save parsed inputs for offline reproduction."""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import time

from app.hunter.main import Hunter
from app.hunter.market import PublicMarket, STEPS
from app.hunter.store import Store
from research.hunter6.forward import audit_page


async def capture(destination: Path, market=None) -> dict:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError('CAPTURE_DESTINATION_NOT_EMPTY')
    destination.mkdir(parents=True,exist_ok=True)
    market=market or PublicMarket()
    try:
        with tempfile.TemporaryDirectory(prefix='aura6-capture-') as folder:
            store=Store(Path(folder)/'observer.sqlite')
            hunter=Hunter(store,market,{'approved':[]})
            await asyncio.wait_for(hunter.cycle(),timeout=45)
            audits=[]
            for frame in STEPS:
                page=store.export_inputs(frame)
                audits.append(audit_page(page))
                (destination/(frame+'.json')).write_text(json.dumps(page,indent=2,allow_nan=False))
            result={'scope':'BOUNDED_PUBLIC_PROBE_NOT_DEPLOYED_OR_CONTINUOUS_FORWARD',
                    'at':time.time(),'error':hunter.error,'frame_errors':hunter.frame_errors,'audits':audits,
                    'states':store.snapshot(time.time(),hunter.quotes,hunter.error),
                    'orders':0,'approved_for_confirmed':[]}
            (destination/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False))
            return result
    finally:await market.close()


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    result=asyncio.run(capture(args.destination))
    print(json.dumps({'error':result['error'],'frame_errors':result['frame_errors'],
                      'inputs_verified':{r['frame']:r['inputs_verified'] for r in result['audits']},'orders':0}))
    if result['error'] or result['frame_errors']:raise SystemExit(1)


if __name__=='__main__':main()
