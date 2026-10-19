"""Add full-year descriptive runs AFTER immutable development/validation selection.

Does not select/optimize from full year or test. Detailed data remain sharded
locally; the terminal receives only a bounded public historical summary.
"""
import argparse,hashlib,json,os,gzip
from pathlib import Path
from scripts.research_active43 import main as research,hashes,simulate,rolling_signals
from scripts.active43_history import load,aggregate,require_spot_protocol
from app.active43.strategies import STEPS


def run(folder):
    require_spot_protocol()
    if os.getenv('RENDER'):raise ValueError('LOCAL_ONLY')
    folder=Path(folder)
    if not (folder/'results.json').exists():research(folder)
    result=json.loads((folder/'results.json').read_text())
    if result['code_hashes']!=hashes():raise ValueError('EXPERIMENT_CODE_CHANGED')
    for row in result['candidates']:
        cfg=row['config'];path=folder/(cfg['timeframe']+'-'+cfg['strategy']+'-full-year.json')
        if path.exists():full=json.loads(path.read_text())
        else:
            bars=aggregate(load(folder/'btc-5m.csv'),STEPS[cfg['timeframe']]);values=rolling_signals(bars,cfg['strategy'],STEPS[cfg['timeframe']])
            full=simulate(bars,values,cfg,result['split']['start'],result['split']['end_exclusive']);path.write_text(json.dumps(full))
        row['full_year']={k:v for k,v in full.items() if k not in ('trades','equity_curve')}
        for segment in ('development','validation','final_test','full_year'):
            row[segment]['policy']=dict(row[segment]['policy'],timeframe=cfg['timeframe'])
        row['daily_equity']=[p for p in full['equity_curve'] if p['time']%86400==0]
        print('FULL_YEAR',cfg['strategy'],cfg['timeframe'],full['metrics']['trades'],full['metrics']['net_profit'],flush=True)
    result['completion_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (folder/'completed-results.json').write_text(json.dumps(result))
    # Summary contains no balances/keys from a real account. All values are
    # explicitly HISTORICAL_ONLY; never merged into a trading ledger.
    target=Path(__file__).resolve().parents[1]/'static'/'active43-research.json'
    for row in result['candidates']:
        if row['config']!=result['selection']['config']:row.pop('daily_equity',None)
    cfg=result['selection']['config']
    source=folder/(cfg['timeframe']+'-'+cfg['strategy']+'-full-year.json')
    historical=json.loads(source.read_text())
    archive=dict(scope='HISTORICAL_BACKTEST_ONLY_NOT_LIVE',production_paper_verified=False,config=cfg,source_sha256=result['source']['csv_sha256'],trades=historical['trades'])
    trade_bytes=json.dumps(archive,separators=(',',':')).encode()
    if len(trade_bytes)>2*1024*1024:raise ValueError('TRADE_ARTIFACT_LIMIT')
    target.with_name('active43-historical-trades.json.gz').write_bytes(gzip.compress(trade_bytes,mtime=0))
    raw=json.dumps(result,ensure_ascii=False,indent=2)
    if len(raw.encode())>2*1024*1024:raise ValueError('PUBLIC_SUMMARY_LIMIT')
    target.write_text(raw+'\n')
    selection_path=Path(__file__).resolve().parents[1]/'app'/'active43'/'selection.json'
    selection_path.write_text(json.dumps(result['selection'],indent=2)+'\n')
    print('COMPLETED',target,selection_path,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',type=Path,required=True);run(p.parse_args().folder)
