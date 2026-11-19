"""Execute displayed reviewer commands without contaminating the artifact tree."""

import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from concretization.workbench import RealizationWorkbench, WorkbenchEnumerationRequest

ROOT = Path(__file__).resolve().parents[1]


def run_displayed_command(command: str, environment: dict[str, str]) -> tuple[int, str, str]:
    process = subprocess.Popen(
        ["bash", "-c", command], cwd=ROOT, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        process.communicate(timeout=5)
        raise
    return process.returncode, stdout, stderr


@pytest.mark.skipif(os.name != "posix", reason="The published shell launcher needs POSIX")
@pytest.mark.parametrize("mode", ["planning", "bundle"])
def test_rendered_command_keeps_exports_outside_the_artifact(
    tmp_path: Path, mode: str,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the rendered commands")
    home = tmp_path / "reviewer home with spaces"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    scratch = tmp_path / "temporary outputs with spaces"
    scratch.mkdir()
    if mode == "planning":
        payload = RealizationWorkbench(ROOT).enumerate_campaign(
            WorkbenchEnumerationRequest(campaign_id="C0045", maximum_realizations=2)
        ).model_dump(mode="json")
        export = downloads / "C0045.realization-space.json"
    else:
        bundle = downloads / "your-bundle.json"
        shutil.copyfile(ROOT / "data/stix/enterprise-attack.json", bundle)
        export = downloads / "C0045.admission.json"
        completed = subprocess.run(
            [sys.executable, "scripts/emulate.py", "C0045", "--bundle", str(bundle),
             "--json-output", str(export)], cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        payload = json.loads(export.read_text())
    export.write_text(json.dumps(payload))
    rendered = subprocess.run(
        [node, str(ROOT / "tests/reviewer_commands.cjs"), mode, str(export)],
        capture_output=True, text=True, check=True, timeout=15,
    ).stdout
    assert '$review_outputs/' in rendered
    assert "untrusted" not in rendered
    assert "bash run.sh" in rendered
    sys.path.insert(0, str(ROOT / "scripts"))
    from public_tree_manifest import collect_files

    before = collect_files(ROOT, "PUBLIC_TREE_SHA256.json")
    environment = {**os.environ, "HOME": str(home), "TMPDIR": str(scratch),
                   "STICKS_PYTHON": sys.executable}
    status, stdout, stderr = run_displayed_command(rendered, environment)
    assert status == 0, stdout + stderr
    assert collect_files(ROOT, "PUBLIC_TREE_SHA256.json") == before
    outputs = list(scratch.rglob("*.json"))
    assert len(outputs) == 1, stdout + stderr
    assert json.dumps(json.loads(outputs[0].read_text()), sort_keys=True) == json.dumps(payload, sort_keys=True)
