"""Bounded closed 15m reads through an injected existing public HTTP transport."""
import asyncio
import time
import json
from .models import Bar,LabError,STEPS,WARMUP_4H,MAX_BASE_BARS,SOURCE,validate_series,number,precise


@precise
def aggregate(bars,step,end):
    validate_series(bars,900,end)
    width=step//900
    if step not in STEPS.values() or len(bars)%width:raise LabError('INVALID_TIMESTAMPS')
    result=[]
    for i in range(0,len(bars),width):
        chunk=bars[i:i+width]
        if chunk[0].time%step:raise LabError('INVALID_TIMESTAMPS')
        result.append(Bar(chunk[0].time,chunk[0].open,max(b.high for b in chunk),min(b.low for b in chunk),chunk[-1].close,sum((b.volume for b in chunk),number('0'))))
    validate_series(result,step,end)
    return result


class Loader:
    def __init__(self,page,clock=time.time):self.page=page;self.clock=clock

    async def fetch(self,start,end):
        now=int(self.clock())
        if type(start) is not int or type(end) is not int or start%14400 or end%14400 or start>=end or end>now:raise LabError('INVALID_RANGE')
        warm_start=start-WARMUP_4H*14400
        count=(end-warm_start)//900
        if warm_start<0 or count>MAX_BASE_BARS:raise LabError('DATA_LIMIT')
        cursor=warm_start;bars=[];excluded=0
        try:
            async with asyncio.timeout(60):
                for _ in range(12):
                    if cursor>=end:break
                    rows=await self.page(dict(symbol='BTCUSDT',interval='15m',startTime=cursor*1000,endTime=end*1000-1,limit=min(1000,(end-cursor)//900)))
                    if not isinstance(rows,list) or len(rows)>1000:raise LabError('INVALID_DATA')
                    if not rows:break
                    accepted=[]
                    for row in rows:
                        if not isinstance(row,list) or len(row)<7 or type(row[0]) is not int or type(row[6]) is not int or row[0]%900000:raise LabError('INVALID_TIMESTAMPS')
                        stamp=row[0]//1000
                        if stamp+900>end or stamp+900>now:
                            excluded+=1;continue
                        if stamp<cursor or row[6]!=(stamp+900)*1000-1:raise LabError('INVALID_TIMESTAMPS')
                        accepted.append(Bar(stamp,*[number(row[k]) for k in (1,2,3,4,5)]))
                    if not accepted:break
                    bars.extend(accepted)
                    validate_series(bars,900,end)
                    cursor=bars[-1].time+900
                if len(bars)!=count or bars[0].time!=warm_start or bars[-1].time+900!=end:raise LabError('INCOMPLETE_HISTORY')
            return dict(symbol='BTCUSDT',source=SOURCE,start=start,end=end,warmup_start=warm_start,
                        base_timeframe='15m',base_count=len(bars),excluded_forming=excluded,bars=[b.data() for b in bars],
                        requested_count=count,actual_common_coverage={'start':start,'end_exclusive':end},history_truncated=False)
        except LabError:raise
        except TimeoutError:raise LabError('FETCH_TIMEOUT') from None
        except Exception:raise LabError('PUBLIC_DATA_UNAVAILABLE') from None


def restore(snapshot):
    if snapshot.get('symbol')!='BTCUSDT' or snapshot.get('source')!=SOURCE:raise LabError('INVALID_DATA')
    start,end=snapshot['start'],snapshot['end']
    if type(start) is not int or type(end) is not int or start%14400 or end%14400 or start>=end:raise LabError('INVALID_RANGE')
    if len(snapshot['bars'])>MAX_BASE_BARS:raise LabError('DATA_LIMIT')
    bars=[Bar.restore(row) for row in snapshot['bars']]
    validate_series(bars,900,end)
    if (len(bars)!=(end-start+WARMUP_4H*14400)//900 or bars[0].time!=start-WARMUP_4H*14400
            or bars[-1].time+900!=end):raise LabError('INCOMPLETE_HISTORY')
    return bars


async def public_page(client,query):
    """Existing public transport, fixed BTC market endpoint, bounded response bytes."""
    async with client.stream('GET','https://data-api.binance.vision/api/v3/klines',params=query) as response:
        response.raise_for_status()
        body=bytearray()
        async for chunk in response.aiter_bytes():
            if len(body)+len(chunk)>1000000:raise LabError('PUBLIC_DATA_UNAVAILABLE')
            body.extend(chunk)
        return json.loads(body)
