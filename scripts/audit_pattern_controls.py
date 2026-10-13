"""Independent accounting review of all delivered control/walk-forward portfolios."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.audit_pattern_research import check
from scripts.run_pattern_research import artifact_read
from scripts.pattern_research import atomic_json,STEPS


def audit(output):
    controls=json.loads((output/'controls.results.json').read_text());prices={};jobs=trades=0
    for row in controls['controls']+controls['walk_forward']:
        if 'metrics' not in row:continue
        tf=row['hypothesis']['timeframe']
        if tf not in prices:
            m=json.loads((output/(tf+'.cache.json')).read_text())
            data=artifact_read(output/(tf+'.cache.gz'),m['sha256'])
            prices.clear();prices[tf]={b['time']:b for p in data for b in p['bars']}
        value=artifact_read(output/row['artifact'],row['sha256'])
        trades+=check(value,'10','5',prices[tf],STEPS[tf]);jobs+=1
    result=dict(jobs_checked=jobs,closed_trades_checked=trades,errors=0,
        scope='All delivered matched random/simple baseline and executed walk-forward test portfolios; training-selection portfolios use engine internal guards, not included in this independent count. Buy-hold is separately risk-non-equivalent.')
    atomic_json(output/'independent.controls.audit.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();print(audit(a.output))
