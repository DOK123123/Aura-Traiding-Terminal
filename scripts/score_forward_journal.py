"""Offline scoring of an integrity-checked complete forward JSONL export."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.forward.models import verify
from app.forward.stats import summarize


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('journal',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.journal.stat().st_size>512*1024*1024:raise ValueError('Offline file limit')
    raw=a.journal.read_bytes();manifest=json.loads(a.journal.with_suffix(a.journal.suffix+'.manifest.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=manifest['sha256']:raise ValueError('Snapshot checksum')
    rows=[json.loads(line) for line in raw.splitlines()]
    if len(rows)!=manifest['total_rows'] or len(rows)>250000 or len({r['id'] for r in rows})!=len(rows):raise ValueError('Snapshot completeness')
    for row in rows:verify(row)
    result=summarize(rows,partial=False);result['source_export_sha256']=manifest['sha256']
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    print('Complete forward snapshot scored; no profitability claim')

if __name__=='__main__':main()
