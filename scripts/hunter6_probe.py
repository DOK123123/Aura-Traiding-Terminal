"""Bounded public GET verification, not a continuous deployed forward test."""
import asyncio
import json
import math
from pathlib import Path
import tempfile
import time

from app.hunter.market import PublicMarket,parse_bars,STEPS,SOURCE
from app.hunter.store import Store
from app.hunter.main import Hunter
from research.hunter6.data import load,aggregate


async def main(destination):
    rows,_,_=load();market=PublicMarket();cross=[]
    try:
        for date in [1640995200,1704067200,1788220800]:
            for frame,step in list(STEPS.items())[1:]:
                raw=await market.get('history-candles',granularity={'1h':'1H','4h':'4H'}.get(frame,frame),limit=10,endTime=date*1000)
                native=parse_bars(raw['data'],step)
                local={b[0]:b for b in aggregate([b for b in rows if date-12*step<=b[0]<=date+step],step)}
                ohlc=bool(native) and all(b[0] in local and all(math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-8) for x,y in zip(b[1:5],local[b[0]][1:5])) for b in native)
                volumes=bool(native) and all(b[0] in local and math.isclose(b[5],local[b[0]][5],rel_tol=1e-8,abs_tol=1e-5) for b in native)
                cross.append({'frame':frame,'end':date,'bars':len(native),'ohlc_match':ohlc,'volume_match':volumes,'max_volume_relative_difference':max([abs(b[5]-local[b[0]][5])/max(1,local[b[0]][5]) for b in native if b[0] in local],default=None)})
                await asyncio.sleep(.22)
        with tempfile.TemporaryDirectory(prefix='aura6-public-probe-') as folder:
            path=Path(folder)/'observer.sqlite';observer=Hunter(Store(path),market,{'approved':[]});cycles=[]
            for restart in [False,True]:
                if restart:observer=Hunter(Store(path),market,{'approved':[]})
                await observer.cycle();d=observer.store.snapshot(time.time(),observer.quotes,observer.error)
                cycles.append({'restart':restart,'at':d['server_time'],'state':d['state'],'fresh_frames':d['fresh_frames'],'records':len(d['records']),'alerts':len(d['alerts']),'error':observer.error,'account_connected':d['account_connected'],'execution_enabled':d['execution_enabled']})
                await asyncio.sleep(.25)
        evidence={'source':SOURCE,'scope':'BOUNDED_PUBLIC_GET_PROBE_NOT_DEPLOYED_FORWARD_PROFIT','crosschecks':cross,'cycles':cycles,'confirmed_eligibility':0,'orders':0}
        Path(destination).write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence))
    finally:await market.close()


if __name__=='__main__':
    import sys
    asyncio.run(main(sys.argv[1] if len(sys.argv)>1 else 'docs/aura6/PUBLIC_PROBE.json'))
