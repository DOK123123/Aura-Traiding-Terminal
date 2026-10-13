"""Independent exact accounting audit of every new research/control portfolio."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.audit_pattern_research import check
from scripts.run_pattern_research import artifact_read
from scripts.pattern_research import atomic_json


def audit(output):
    meta=json.loads((output/'states.json.meta.json').read_text())
    data=artifact_read(output/'states.json.gz',meta['sha256'])
    prices={b['time']:b for p in data for b in p['bars']};del data
    state=json.loads((output/'checkpoint.json').read_text());count=trades=0
    for key,record in state['jobs'].items():
        value=artifact_read(output/record['artifact'],record['sha256']);stress=' |stress|' in key
        trades+=check(value,'20' if stress else '10','10' if stress else '5',prices,900);count+=1
    result=dict(jobs_checked=count,closed_trades_checked=trades,errors=0,
        method='Independent Fraction adverse-fill verification, Decimal commission/PnL/risk, next-open, SL/TP/gap touches, one-position overlap, cash reconstruction, mark-to-market equity and drawdown. Conditional gap outcomes are not asserted investable.')
    atomic_json(output/'independent.audit.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();print(audit(a.output))
