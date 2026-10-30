"""Offline audit of a saved /api/hunter/inputs JSON page (no network requests)."""
import argparse
import json
from pathlib import Path

from research.hunter6.forward import audit_page


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export',type=Path)
    args=parser.parse_args()
    if args.export.stat().st_size>20_000_000:raise ValueError('EXPORT_SIZE_LIMIT')
    print(json.dumps(audit_page(json.loads(args.export.read_text())),indent=2))


if __name__=='__main__':main()
