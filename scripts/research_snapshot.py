"""Offline transfer; no HTTP write route, deploy, SQL import or production access."""
import argparse
import getpass
import hmac
import json
import os
from pathlib import Path
from app.lab.models import LabError
from app.research.snapshot import SnapshotStore, export_snapshot, publish_snapshot


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    ex = sub.add_parser('export'); ex.add_argument('--state-dir', type=Path, required=True); ex.add_argument('--job-id', required=True); ex.add_argument('--output', type=Path, required=True)
    ve = sub.add_parser('verify'); ve.add_argument('--bundle', type=Path, required=True)
    pu = sub.add_parser('publish'); pu.add_argument('--bundle', type=Path, required=True); pu.add_argument('--checksum', required=True); pu.add_argument('--owner-approved-publication', action='store_true')
    a = p.parse_args(argv)
    try:
        if os.getenv('RENDER'): raise LabError('RESEARCH_LOCAL_WORKBENCH_REQUIRED')
        if a.command == 'verify': result = SnapshotStore(a.bundle).verify()
        else:
            configured = os.getenv('AURA_TESTNET_VIEW_PASSWORD', '')
            if len(configured) < 12 or not hmac.compare_digest(getpass.getpass('Local owner password: '), configured): raise LabError('OWNER_AUTH_REQUIRED')
            if a.command == 'publish':
                if not a.owner_approved_publication: raise LabError('OWNER_PUBLICATION_REVIEW_REQUIRED')
                result = publish_snapshot(a.bundle, a.checksum)
            else:
                from scripts.research_runner import state_store
                result = export_snapshot(state_store(a.state_dir, readonly=True), a.job_id, a.output)
        print(json.dumps(result)); return 0
    except (LabError, OSError, ValueError, TypeError, KeyError, EOFError) as e:
        print(json.dumps(dict(status='ERROR', code=e.code if isinstance(e,LabError) else 'SNAPSHOT_UNAVAILABLE'))); return 1

if __name__ == '__main__': raise SystemExit(main())
