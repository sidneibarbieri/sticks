"""The public live entry point must observe and seal a typed target run."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_runtime(tmp_path):
    executable = tmp_path / "python-fixture"
    executable.write_text(r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
if sys.argv[1:2] in (['-c'], ['-']):
    raise SystemExit(0)
with Path(os.environ['STICKS_TEST_CALLS']).open('a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\n')
if os.environ.get('STICKS_TEST_FAIL') == sys.argv[1]:
    raise SystemExit(9)
""")
    executable.chmod(0o700)
    calls = tmp_path / "calls.jsonl"
    environment = {"PATH": os.environ["PATH"], "STICKS_PYTHON": str(executable),
                   "STICKS_TEST_CALLS": str(calls)}
    return environment, calls


def test_run_observes_after_execution_in_the_same_run_root(fake_runtime, tmp_path):
    environment, calls = fake_runtime
    run_root = str(tmp_path / "new-run")
    result = subprocess.run(['bash', 'artifact/run.sh', '--run-root', run_root],
                            cwd=ROOT, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert [json.loads(line) for line in calls.read_text().splitlines()] == [
        ['scripts/run_isolated_lab_campaign.py', '--campaign', '0.c0026', '--provider', 'qemu',
         '--run-root', run_root, '--keep-lab'],
        ['scripts/complete_c0026_run.py', '--run-root', run_root],
    ]


def test_failed_execution_cannot_start_completion(fake_runtime, tmp_path):
    environment, calls = fake_runtime
    environment['STICKS_TEST_FAIL'] = 'scripts/run_isolated_lab_campaign.py'
    result = subprocess.run(['bash', 'artifact/run.sh', '--run-root', str(tmp_path / 'new-run')],
                            cwd=ROOT, env=environment, capture_output=True, text=True)
    assert result.returncode == 9
    assert len(calls.read_text().splitlines()) == 1


def test_validate_only_verifies_the_selected_final_receipt(fake_runtime, tmp_path):
    environment, calls = fake_runtime
    run_root = str(tmp_path / 'completed-run')
    result = subprocess.run(['bash', 'artifact/validate.sh', '--run-root', run_root],
                            cwd=ROOT, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(calls.read_text()) == [
        'scripts/finalize_isolated_lab_run.py', '--run-root', run_root, '--verify']


@pytest.mark.parametrize('script', ['run.sh', 'validate.sh'])
def test_live_entrypoints_require_an_explicit_run_root(script):
    result = subprocess.run(['bash', 'artifact/' + script], cwd=ROOT, capture_output=True)
    assert result.returncode == 2
