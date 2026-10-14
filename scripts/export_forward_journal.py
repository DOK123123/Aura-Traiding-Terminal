"""Owner-authenticated paginated JSONL snapshot export. Credentials stay in env."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import httpx
from app.forward.models import ForwardError,verify


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('url');p.add_argument('output',type=Path);a=p.parse_args()
    parsed=urlsplit(a.url)
    if parsed.scheme!='https' or parsed.hostname!='terminal.onrender.com' or parsed.port is not None or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise SystemExit('Use an HTTPS terminal origin without credentials')
    password=os.getenv('AURA_TESTNET_VIEW_PASSWORD','')
    if len(password)<12:raise SystemExit('Owner password not configured in environment')
    if a.output.exists():raise SystemExit('Refuse to overwrite an existing export')
    # Standalone client: suppress transport logging rather than disclose owner Basic.
    import logging
    logging.disable(logging.CRITICAL)
    rows=[];after=0;through=None;total=None
    try:
        with httpx.Client(timeout=30,follow_redirects=False,auth=('aura',password)) as client:
            for _ in range(1250): # <=250000 rows; finite, explicit limit
                params=dict(after=after,limit=200)
                if through is not None:params['through']=through
                with client.stream('GET',a.url.rstrip('/')+'/api/intelligence/forward/export',params=params) as response:
                    response.raise_for_status();body=bytearray()
                    for chunk in response.iter_bytes():
                        if len(body)+len(chunk)>2*1024*1024:raise ValueError('Page limit')
                        body.extend(chunk)
                value=json.loads(body)
                if through is None:through=value['through'];total=value['snapshot_total_rows']
                for row in value['rows']:verify(row)
                rows.extend(value['rows'])
                if value['complete']:break
                if value['next_cursor']<=after:raise ValueError('Cursor stalled')
                after=value['next_cursor']
            else:raise ValueError('Export limit reached; no partial export published')
        if len(rows)!=total:raise ValueError('Snapshot row count mismatch')
        raw=''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows).encode()
        a.output.write_bytes(raw)
        a.output.with_suffix(a.output.suffix+'.manifest.json').write_text(json.dumps(dict(through=through,total_rows=total,sha256=hashlib.sha256(raw).hexdigest()),indent=2))
        print('Verified forward snapshot exported:',len(rows),'rows')
    except (httpx.HTTPError,ValueError,KeyError,ForwardError):raise SystemExit('Export failed; check owner access and limits (no credentials logged)') from None

if __name__=='__main__':main()
