"""Exercise the running engine against real providers; no synthetic fallback."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import httpx


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--output',default='pattern-check.json')
    args=parser.parse_args()
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
    failed=False
    with httpx.Client(base_url=args.base_url,timeout=150,trust_env=False) as client:
        for symbol in ('XAUUSD','BTCUSDT'):
            for tf in ('1m','5m','15m','1h'):
                for context in (500,2000):
                    start=time.monotonic()
                    market=client.get('/api/market',params={'symbol':symbol,'timeframe':tf,'limit':context})
                    market_data=market.json()
                    response=client.post('/api/patterns/analyze',json={'symbol':symbol,'timeframe':tf,'context':context,
                                                                  'chart_source':market_data.get('source')})
                    data=response.json()
                    row=dict(symbol=symbol,timeframe=tf,context=context,http_status=response.status_code,
                             elapsed=round(time.monotonic()-start,2))
                    if response.is_success:
                        assert data['signal'] in ('LONG','SHORT','WAIT')
                        assert data['archive_bars']>=context
                        assert all(s['up']+s['down']+s['flat']==data['historical_matches'] for s in data['outcomes'].values())
                        row.update({k:data[k] for k in ('status','source','archive_bars','as_of','signal','confidence','historical_matches','average_similarity','outcomes')})
                    else:
                        assert data.get('status')=='NO DATA'
                        row['error']=data; failed=True
                    report['checks'].append(row)
                    print(json.dumps({k:v for k,v in row.items() if k!='outcomes'},ensure_ascii=True),flush=True)
                    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            # Historical-point prediction with separately attached realized returns.
            body={'symbol':symbol,'timeframe':'15m','context':500}
            baseline=client.post('/api/patterns/analyze',json=body).json()
            if baseline.get('archive_last'):
                point=client.post('/api/patterns/analyze',json={**body,'as_of':baseline['archive_last']-100*900}).json()
                assert point.get('mode')=='POINT REPLAY', point
                backtest=client.post('/api/patterns/backtest',json={**body,'max_points':10}).json()
                assert backtest.get('status')=='OK', backtest
                report.setdefault('replays',[]).append(dict(symbol=symbol,point=point,backtest=backtest))
                print(json.dumps({'symbol':symbol,'backtest':backtest['summary']},ensure_ascii=True),flush=True)
                Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return int(failed)


if __name__=='__main__':raise SystemExit(main())
