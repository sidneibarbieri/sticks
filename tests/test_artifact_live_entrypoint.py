"""The public live entry point must preflight, observe, seal and verify a typed target run."""

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
if os.environ.get('STICKS_TEST_CONTEXT') == sys.argv[1] and '--run-root' in sys.argv:
    run_root = Path(sys.argv[sys.argv.index('--run-root') + 1])
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / 'run_context.json').write_text('{}')
if os.environ.get('STICKS_TEST_FAIL') == sys.argv[1]:
    raise SystemExit(9)
if sys.argv[1].startswith('scripts/complete_') and '--run-root' in sys.argv:
    run_root = Path(sys.argv[sys.argv.index('--run-root') + 1])
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / 'final_run_receipt.json').write_text('{}')  # completion seals the run
""")
    executable.chmod(0o700)
    calls = tmp_path / "calls.jsonl"
    environment = {"PATH": os.environ["PATH"], "STICKS_PYTHON": str(executable),
                   "STICKS_TEST_CALLS": str(calls)}
    return environment, calls


def recorded(calls):
    return [json.loads(line) for line in calls.read_text().splitlines()]


def test_run_preflights_executes_observes_and_verifies_in_one_run_root(fake_runtime, tmp_path):
    environment, calls = fake_runtime
    run_root = str(tmp_path / "new-run")
    result = subprocess.run(['bash', 'artifact/run.sh', '--run-root', run_root],
                            cwd=ROOT, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert recorded(calls) == [
        ['scripts/doctor.py', '--path', 'lab', '--run-root', run_root],
        ['scripts/run_isolated_lab_campaign.py', '--campaign', '0.c0026', '--provider', 'qemu',
         '--run-root', run_root, '--caldera-dispatch', '--keep-lab'],
        ['scripts/complete_c0026_run.py', '--run-root', run_root],
        ['scripts/finalize_isolated_lab_run.py', '--run-root', run_root, '--verify'],
    ]
    assert "PASS" in result.stdout


def test_failed_preflight_creates_nothing(fake_runtime, tmp_path):
    environment, calls = fake_runtime
    environment['STICKS_TEST_FAIL'] = 'scripts/doctor.py'
    result = subprocess.run(['bash', 'artifact/run.sh', '--run-root', str(tmp_path / 'new-run')],
                            cwd=ROOT, env=environment, capture_output=True, text=True)
    assert result.returncode == 3
    assert len(recorded(calls)) == 1
    assert not (tmp_path / 'new-run').exists()


def test_failed_execution_before_a_run_exists_cannot_start_completion(fake_runtime, tmp_path):
    environment, calls = fake_runtime
    environment['STICKS_TEST_FAIL'] = 'scripts/run_isolated_lab_campaign.py'
    result = subprocess.run(['bash', 'artifact/run.sh', '--run-root', str(tmp_path / 'new-run')],
                            cwd=ROOT, env=environment, capture_output=True, text=True)
    assert result.returncode == 9
    assert [call[0] for call in recorded(calls)] == [
        'scripts/doctor.py', 'scripts/run_isolated_lab_campaign.py']


def test_failed_campaign_after_provisioning_still_tears_down_and_fails(fake_runtime, tmp_path):
    environment, calls = fake_runtime
    environment['STICKS_TEST_CONTEXT'] = 'scripts/run_isolated_lab_campaign.py'
    environment['STICKS_TEST_FAIL'] = 'scripts/run_isolated_lab_campaign.py'
    result = subprocess.run(['bash', 'artifact/run.sh', '--run-root', str(tmp_path / 'new-run')],
                            cwd=ROOT, env=environment, capture_output=True, text=True)
    assert result.returncode == 1
    assert [call[0] for call in recorded(calls)] == [
        'scripts/doctor.py', 'scripts/run_isolated_lab_campaign.py',
        'scripts/complete_c0026_run.py', 'scripts/finalize_isolated_lab_run.py']


def test_unsealed_run_is_reported_without_verifying_a_missing_receipt(fake_runtime, tmp_path):
    environment, calls = fake_runtime
    environment['STICKS_TEST_CONTEXT'] = 'scripts/run_isolated_lab_campaign.py'
    environment['STICKS_TEST_FAIL'] = 'scripts/complete_c0026_run.py'
    result = subprocess.run(['bash', 'artifact/run.sh', '--run-root', str(tmp_path / 'new-run')],
                            cwd=ROOT, env=environment, capture_output=True, text=True)
    assert result.returncode == 1
    assert [call[0] for call in recorded(calls)] == [
        'scripts/doctor.py', 'scripts/run_isolated_lab_campaign.py', 'scripts/complete_c0026_run.py']
    assert "no sealed receipt" in result.stdout
    assert "PASS" not in result.stdout


def test_costaricto_uses_the_sticks_transport(fake_runtime, tmp_path):
    environment, calls = fake_runtime
    run_root = str(tmp_path / 'new-run')
    result = subprocess.run(['bash', 'artifact/run.sh', '--run-root', run_root,
                             '--campaign', '0.costaricto'],
                            cwd=ROOT, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    runner, completion = recorded(calls)[1:3]
    assert '--caldera-dispatch' not in runner
    assert completion == ['scripts/complete_costaricto_run.py', '--run-root', run_root]


def test_campaign_without_typed_contract_is_refused_before_anything_runs(fake_runtime, tmp_path):
    environment, calls = fake_runtime
    result = subprocess.run(['bash', 'artifact/run.sh', '--run-root', str(tmp_path / 'r'),
                             '--campaign', '0.shadowray'],
                            cwd=ROOT, env=environment, capture_output=True, text=True)
    assert result.returncode == 2
    assert not calls.exists()


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
