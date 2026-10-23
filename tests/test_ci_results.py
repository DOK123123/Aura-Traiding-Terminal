"""CI must not report skipped/absent tests as successful verification."""
from pathlib import Path
import importlib.util
import pytest

spec = importlib.util.spec_from_file_location('ci_results', Path('ci/check_results.py'))
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.mark.parametrize('body', [
    '<testsuites/>',
    '<testsuite skipped="1"><testcase/></testsuite>',
    '<testsuite><testcase><skipped/></testcase></testsuite>',
    '<testsuite><testcase><failure/></testcase></testsuite>',
    '<testsuite errors="1"><testcase/></testsuite>',
])
def test_missing_skipped_failed_reports_reject_ci_pass(tmp_path, body):
    path = tmp_path/'result.xml';path.write_text(body)
    with pytest.raises(ValueError):checker.result(path)


def test_completed_tests_and_runtime_lock_are_required(tmp_path):
    path=tmp_path/'result.xml';path.write_text('<testsuites><testsuite><testcase name="done"/></testsuite></testsuites>')
    assert checker.result(path)['tests']==1
    checker.check_lock(Path('requirements.txt'),Path('ci/requirements.lock'))
