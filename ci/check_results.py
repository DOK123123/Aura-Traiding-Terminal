"""A successful regression gate requires actual tests and zero skips/failures."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def result(path: Path) -> dict:
    root = ET.parse(path).getroot()
    cases = list(root.iter('testcase'))
    if not cases:
        raise ValueError(f'EMPTY_TEST_REPORT: {path.name}')
    for item in root.iter():
        if item.tag in ('skipped', 'failure', 'error'):
            raise ValueError(f'REGRESSION_NOT_PASSED: {path.name}: {item.tag}')
        for key in ('skipped', 'failures', 'errors', 'disabled', 'todo'):
            if int(item.get(key, '0')):
                raise ValueError(f'REGRESSION_NOT_PASSED: {path.name}: {key}')
    return dict(report=path.name, tests=len(cases), skipped=0, failures=0)


def check_lock(runtime: Path, lock: Path) -> None:
    def pins(path):
        values = {}
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            name, version = line.split('==')
            if not name or not version or any(c in version for c in '<>*,; '):
                raise ValueError('DEPENDENCY_MUST_BE_EXACTLY_PINNED')
            values[name.lower().replace('_', '-')] = version
        return values
    required, frozen = pins(runtime), pins(lock)
    if any(frozen.get(name) != version for name, version in required.items()):
        raise ValueError('CI_LOCK_DOES_NOT_MATCH_RUNTIME_REQUIREMENTS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='*', type=Path)
    args = parser.parse_args()
    check_lock(Path('requirements.txt'), Path('ci/requirements.lock'))
    if args.reports:
        summary = dict(status='CI_PASS', reports=[result(p) for p in args.reports])
        print(json.dumps(summary))
        Path('ci-results/summary.json').write_text(json.dumps(summary, indent=2) + '\n')
