"""Build compact real replay + past-only event index; never train on2025."""
from pathlib import Path
import argparse,hashlib,json,sys
from decimal import Decimal as D
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.lab.models import Baseline,canonical
from app.lab.execution import simulate
from app.lab.strategies import Decision
from scripts.lab3_history import load_years
from scripts.run_six_year import segments
from scripts.lab3_strategies import higher
from app.intelligence.patterns import features,detect
from app.intelligence.analysis import CONFIG,analyze
from scripts.run_lab3 import stamp


def build(path):
    raw,meta=load_years(path,allow_gaps=True);training_end=stamp('2023-01-01');events=[]
    for tf,step in [('15m',900),('1h',3600),('4h',14400)]:
        horizon=CONFIG['horizon_days']*86400//step
        for part in segments([b for b in raw if b.time<training_end]):
            bars=part if tf=='15m' else higher(part,step)
            for i in range(200,len(bars)-horizon-2,horizon):
                prefix=bars[max(0,i-249):i+1];ctx=features(prefix);ps=detect(prefix,timeframe=tf)
                for direction in ('LONG','SHORT'):
                    ds=[Decision() for _ in bars[i:i+horizon+2]];ds[0]=Decision(direction,bars[i].close*D('.02'),bars[i].close*D('.04'))
                    ds[horizon]=Decision(exit_long=direction=='LONG',exit_short=direction=='SHORT')
                    run=simulate(bars[i:i+horizon+2],ds,0,len(ds),step,Baseline(),close_at_end=False)
                    if not run['trades']:continue
                    t=run['trades'][0]
                    if t['exit_time']>=training_end:continue
                    events.append(dict(timestamp=bars[i].time+step,resolved_at=t['exit_time'],timeframe=tf,direction=direction,vector=ctx['vector'],patterns=[p['pattern_id'] for p in ps],net_pnl=t['realized_pnl'],target_first=t['exit_reason'].startswith('TAKE_PROFIT')))
    replay=[b for b in raw if stamp('2022-11-15')<=b.time<stamp('2023-02-01')]
    if len(segments(replay))!=1:raise ValueError('Replay must be continuous')
    pack=dict(version='ADAPTIVE_INTELLIGENCE_1.0',config=CONFIG,source='User supplied Binance Spot archives; SHA verified internally',archive_sha256=meta['bundle_sha256'],training_end=training_end,
        replay_start=stamp('2023-01-01'),replay_end=stamp('2023-02-01'),bars=[b.data() for b in replay],index=events,smoke=None)
    for i,b in enumerate(replay):
        if b.time<pack['replay_start']:continue
        result=analyze(replay[max(0,i-249):i+1],events,'15m')
        if result['strategy']!='WAIT':
            pack['smoke']=dict(timeframe='15m',candle_time=b.time,strategy=result['strategy'],evidence=result['evidence'],note='First eligible chronological replay event; not chosen by future trade PnL. Experimental, not validated live.')
            break
    return pack


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    if a.output.exists():p.error('New output required')
    pack=build(a.archive);a.output.write_bytes(canonical(pack));print({'events':len(pack['index']),'bars':len(pack['bars']),'smoke':pack['smoke'],'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()})
