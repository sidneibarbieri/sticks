"""Check real stop signals at the later completion boundary without VMs."""

import os
from pathlib import Path
import select
import signal
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHILD = """
import importlib
import json
from pathlib import Path
import signal
import sys
module=importlib.import_module('scripts.complete_'+sys.argv[1]+'_run')
root=Path(sys.argv[2])
(root/'evidence').mkdir(parents=True)
(root/'run_context.json').write_text(json.dumps({'campaign_id':'0.'+sys.argv[1], 'keep_lab_requested':True, 'exit_code':0,'source_tree_sha256':'fixture'}))
def observe(run_root):
    print('READY',flush=True)
    signal.pause()
def destroy(run_root):
    (run_root/'cleanup-attempted').write_text('owned-fixture-only')
module.observe_target=observe
module.destroy_lab=destroy
sys.argv=['completion','--run-root',str(root)]
module.main()
"""


@pytest.mark.skipif(os.name != "posix", reason="POSIX lab stop signals")
@pytest.mark.parametrize("campaign", ["c0010", "c0026", "costaricto"])
@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_completion_attempts_owned_cleanup_on_stop(
    tmp_path: Path, campaign: str, stop_signal: signal.Signals
) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", CHILD, campaign, str(tmp_path / "run")],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        ready, _, _ = select.select([process.stdout], [], [], 5)
        assert ready
        assert process.stdout.readline().strip() == "READY"
        os.killpg(process.pid, stop_signal)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode != 0, (stdout, stderr)
        assert (tmp_path / "run/cleanup-attempted").is_file(), (
            process.returncode,
            stderr,
        )
        assert not (tmp_path / "run/final_run_receipt.json").exists()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
