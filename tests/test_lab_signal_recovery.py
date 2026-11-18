"""Send real stop signals to a runner whose infrastructure commands are stubbed."""

import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys

import pytest

from scripts import run_lab_campaign as runner
from scripts import lab_shutdown

ROOT = Path(__file__).resolve().parents[1]
SIGNAL_RUNNER = """
import json
from pathlib import Path
import signal
import sys
from scripts import run_lab_campaign as runner

log = Path(sys.argv[2])
def record(label):
    with log.open('a') as output:
        output.write(json.dumps(label) + '\\n')
class Snapshot:
    def restore(self): record('snapshot restored')
    def discard(self): record('snapshot discarded')
def run_command(command, label, environment=None):
    record(label)
    if label == sys.argv[1]:
        print('READY', flush=True)
        signal.pause()
runner._run_command = run_command
runner._log = lambda message: None
runner._capture_derived_state = Snapshot
runner._cleanup_runtime_outputs = lambda: record('outputs cleaned')
arguments = ['--campaign', '0.c0026', '--keep-lab', '--skip-collect-evidence']
if sys.argv[3] == 'preexisting': arguments.append('--assume-lab-running')
runner.main(arguments)
"""


@pytest.mark.skipif(os.name != "posix", reason="POSIX lab stop signals")
@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize(
    ("stage", "ownership"),
    [
        ("bring up lab", "owned"),
        ("execute campaign", "owned"),
        ("execute campaign", "preexisting"),
    ],
)
def test_stop_signal_cleans_only_owned_lab(
    tmp_path: Path, stop_signal: signal.Signals, stage: str, ownership: str
) -> None:
    log = tmp_path / "calls.jsonl"
    process = subprocess.Popen(
        [sys.executable, "-c", SIGNAL_RUNNER, stage, str(log), ownership],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert process.stdout is not None
        readable, _, _ = select.select([process.stdout], [], [], 5)
        assert readable, "Fixture runner did not reach the requested stage"
        assert process.stdout.readline().strip() == "READY"
        os.killpg(process.pid, stop_signal)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode != 0, (stdout, stderr)
        if stop_signal == signal.SIGTERM:
            assert process.returncode == 128 + stop_signal
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        assert ("tear down lab" in calls) == (ownership == "owned"), calls
        assert "snapshot restored" in calls, calls
        assert "outputs cleaned" in calls, calls
        assert "snapshot discarded" not in calls, calls
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)


@pytest.mark.parametrize("interrupted", [False, True])
def test_main_restores_the_callers_signal_handler(
    monkeypatch: pytest.MonkeyPatch, interrupted: bool
) -> None:
    original_handler = signal.getsignal(signal.SIGTERM)

    def execute(arguments: object) -> int:
        assert signal.getsignal(signal.SIGTERM) is lab_shutdown._request_shutdown
        if interrupted:
            raise KeyboardInterrupt
        return 0

    monkeypatch.setattr(runner, "run_lab_campaign", execute)
    if interrupted:
        with pytest.raises(KeyboardInterrupt):
            runner.main(["--campaign", "0.c0026"])
    else:
        assert runner.main(["--campaign", "0.c0026"]) == 0
    assert signal.getsignal(signal.SIGTERM) == original_handler
