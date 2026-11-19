"""Stop the real Bash entry points while their infrastructure stages are stubbed."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = r"""#!/usr/bin/env python3
import json,os,signal,sys,time
from pathlib import Path
if sys.argv[1:2] in (['-c'], ['-']):
    raise SystemExit(0)
script = sys.argv[1]
root = Path(os.environ['STICKS_STOP_FIXTURE'])
with (root/'calls.jsonl').open('a') as output:
    output.write(json.dumps(script)+'\n')
run = root/'run'
resource = run/'owned-resource'
if script == 'scripts/run_isolated_lab_campaign.py':
    run.mkdir()
    (run/'run_context.json').write_text(json.dumps({'exit_code':0}))
    resource.write_text('fixture-only')
    if os.environ.get('STICKS_STOP_NO_CONTEXT') == '1':
        (run/'run_context.json').unlink()
        raise SystemExit(9)
if script == os.environ['STICKS_STOP_STAGE']:
    def stop(number,frame):
        (root/'stop-forwarded').write_text(str(number))
        with (root/'signals.jsonl').open('a') as output:
            output.write(json.dumps(number)+'\n')
        if script.endswith('run_isolated_lab_campaign.py'):
            (run/'run_context.json').write_text(json.dumps({'exit_code':128+number}))
        if os.environ.get('STICKS_STOP_WAIT_RELEASE') == '1':
            (root/'cleanup-waiting').write_text('ready')
            deadline=time.monotonic()+5
            while not (root/'release-cleanup').exists() and time.monotonic()<deadline:
                time.sleep(.01)
            if not (root/'release-cleanup').exists():
                raise SystemExit(88)
        raise SystemExit(128+number)
    signal.signal(signal.SIGINT,stop)
    signal.signal(signal.SIGTERM,stop)
    (root/'ready').write_text(str(os.getpid()))
    try:
        signal.pause()
    finally:
        if script.startswith('scripts/complete_'):
            resource.unlink(missing_ok=True)
if script.startswith('scripts/complete_'):
    resource.unlink(missing_ok=True)
    (run/'final_run_receipt.json').write_text('{}')
if script == 'scripts/finalize_isolated_lab_run.py':
    if resource.exists() or json.loads((run/'run_context.json').read_text())['exit_code']:
        raise SystemExit(7)
"""


@pytest.mark.skipif(os.name != "posix", reason="POSIX lab stop signals")
@pytest.mark.parametrize("entry", ["artifact/run.sh", "run.sh"])
@pytest.mark.parametrize(
    "stage",
    [
        "scripts/doctor.py",
        "scripts/run_isolated_lab_campaign.py",
        "scripts/complete_c0026_run.py",
    ],
)
@pytest.mark.parametrize(
    "stop_signal", [signal.SIGINT, signal.SIGTERM], ids=["sigint", "sigterm"]
)
def test_cli_stop_waits_for_child_and_preserves_cleanup(
    tmp_path: Path, entry: str, stage: str, stop_signal: signal.Signals
) -> None:
    runtime = tmp_path / "python-fixture"
    runtime.write_text(RUNTIME)
    runtime.chmod(0o700)
    command = ["bash", entry]
    if entry == "run.sh":
        command.append("lab")
    command.extend(["--run-root", str(tmp_path / "run")])
    environment = {
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        "HOME": str(tmp_path),
        "STICKS_PYTHON": str(runtime),
        "STICKS_STOP_FIXTURE": str(tmp_path),
        "STICKS_STOP_STAGE": stage,
    }
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while (
            not (tmp_path / "ready").exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert (tmp_path / "ready").exists(), (
            "CLI fixture did not reach its requested stage"
        )
        os.kill(process.pid, stop_signal)
        process.wait(timeout=5)
        assert (tmp_path / "stop-forwarded").exists(), (
            "Stop was not forwarded to the owned stage"
        )
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 128 + stop_signal, (stdout, stderr)
        assert not (tmp_path / "run/owned-resource").exists(), (
            "Owned fixture resource was retained"
        )
        calls = [
            json.loads(line)
            for line in (tmp_path / "calls.jsonl").read_text().splitlines()
        ]
        if stage == "scripts/doctor.py":
            assert not (tmp_path / "run").exists()
            assert "scripts/complete_c0026_run.py" not in calls
        else:
            assert "scripts/complete_c0026_run.py" in calls
        assert "PASS:" not in stdout
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate(timeout=5)


def test_missing_context_does_not_claim_that_no_resources_were_created(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "python-fixture"
    runtime.write_text(RUNTIME)
    runtime.chmod(0o700)
    environment = {
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        "HOME": str(tmp_path),
        "STICKS_PYTHON": str(runtime),
        "STICKS_STOP_FIXTURE": str(tmp_path),
        "STICKS_STOP_STAGE": "not-paused",
        "STICKS_STOP_NO_CONTEXT": "1",
    }
    result = subprocess.run(
        ["bash", "artifact/run.sh", "--run-root", str(tmp_path / "run")],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 9
    assert "Cleanup is not certified" in result.stderr
    assert str(tmp_path / "run") in result.stderr
    assert "nothing to tear down" not in result.stderr
    assert (tmp_path / "run/owned-resource").is_file()


def test_latched_stop_blocks_new_work_but_allows_recovery(tmp_path: Path) -> None:
    script = r"""
set -eu
before_flags="$-"
source "$1"
sticks_request_stop 143
if sticks_run_stage "$2" -c 'from pathlib import Path; import sys; Path(sys.argv[1]).write_text("unexpected")' "$3/new-work"; then
  exit 99
else
  stage_status=$?
fi
sticks_run_cleanup_stage "$2" -c 'from pathlib import Path; import sys; Path(sys.argv[1]).write_text("cleaned")' "$3/recovery"
[[ "$before_flags" == "$-" ]] || exit 98
printf '%s %s\n' "$stage_status" "$STICKS_STOP_STATUS"
"""
    result = subprocess.run(
        [
            "bash",
            "-c",
            script,
            "lifecycle-test",
            str(ROOT / "scripts/shell_lifecycle.sh"),
            sys.executable,
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "143 143"
    assert not (tmp_path / "new-work").exists()
    assert (tmp_path / "recovery").read_text() == "cleaned"


@pytest.mark.skipif(os.name != "posix", reason="POSIX lab stop signals")
def test_second_stop_does_not_interrupt_cleanup(tmp_path: Path) -> None:
    runtime = tmp_path / "python-fixture"
    runtime.write_text(RUNTIME)
    runtime.chmod(0o700)
    environment = {
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        "HOME": str(tmp_path),
        "STICKS_PYTHON": str(runtime),
        "STICKS_STOP_FIXTURE": str(tmp_path),
        "STICKS_STOP_STAGE": "scripts/run_isolated_lab_campaign.py",
        "STICKS_STOP_WAIT_RELEASE": "1",
    }
    errors = tmp_path / "stderr.log"
    with errors.open("w") as error_stream:
        process = subprocess.Popen(
            ["bash", "run.sh", "lab", "--run-root", str(tmp_path / "run")],
            cwd=ROOT,
            env=environment,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=error_stream,
            text=True,
        )
        try:
            deadline = time.monotonic() + 5
            while (
                not (tmp_path / "ready").exists()
                and process.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert (tmp_path / "ready").exists()
            os.kill(process.pid, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while (
                not (tmp_path / "cleanup-waiting").exists()
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert (tmp_path / "cleanup-waiting").exists()
            os.kill(process.pid, signal.SIGINT)
            deadline = time.monotonic() + 5
            while (
                "no second signal forwarded" not in errors.read_text()
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert "no second signal forwarded" in errors.read_text()
            assert process.poll() is None
            (tmp_path / "release-cleanup").write_text("continue")
            stdout, _ = process.communicate(timeout=5)
            assert process.returncode == 143
            assert not (tmp_path / "run/owned-resource").exists()
            assert "PASS:" not in stdout
            assert (tmp_path / "signals.jsonl").read_text().splitlines() == ["15"]
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate(timeout=5)
