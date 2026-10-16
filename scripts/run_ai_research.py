"""Manual reproducible offline Research Lab cycle; never constructs a trading store."""
import argparse
from datetime import datetime,timezone
import gzip
from pathlib import Path
from app.lab.models import canonical,digest
from app.research.data import load_dataset
from app.research.registry import HYPOTHESES,PROTOCOL
from app.research.experiment import frozen_config,execute


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path);p.add_argument('--hypothesis',choices=list(HYPOTHESES)+['ALL'],default='ALL');a=p.parse_args(argv)
    a.output_dir.mkdir(parents=True,exist_ok=True);plan_path=a.output_dir/'frozen_plan.json'
    bars,source=load_dataset();names=list(HYPOTHESES) if a.hypothesis=='ALL' else [a.hypothesis]
    configs={name:frozen_config(name,source) for name in names}
    plan=dict(frozen_before_metrics=True,frozen_at_utc=datetime.now(timezone.utc).isoformat(),protocol=PROTOCOL,
        configs=configs,config_hashes={k:digest(v) for k,v in configs.items()},source=source)
    # Never overwrite the pre-metrics plan or previous results.
    with plan_path.open('xb') as f:f.write(canonical(plan))
    summaries=[]
    for name,config in configs.items():
        report=execute(config,bars,source);raw=canonical(report)
        with (a.output_dir/(name+'.json.gz')).open('xb') as f:f.write(gzip.compress(raw,mtime=0))
        item=dict(hypothesis=name,status=report['auditor']['status'],auditor=report['auditor'],config_hash=report['config_hash'],checksum=report['checksum'],
            runs=[dict(split=r['split'],scale=r['scale'],metrics=r['metrics']) for r in report['runs']])
        summaries.append(item);print(name,report['auditor']['status'],flush=True)
    summary=dict(title='AURA AI RESEARCH LAB v1',independent_test_available=False,candidate_for_paper_enabled=False,
        source=source,plan_hash=digest(plan),experiments=summaries)
    summary['checksum']=digest(summary)
    with (a.output_dir/'summary.json').open('xb') as f:f.write(canonical(summary))

if __name__=='__main__':main()
