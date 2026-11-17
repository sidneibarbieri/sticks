"""Verify CLI recomputation of the planning object exported by the workbench."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from concretization.workbench import RealizationWorkbench, WorkbenchEnumerationRequest

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_realization_workbench.py"),
            *arguments,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture
def exported_result(tmp_path: Path) -> Path:
    response = RealizationWorkbench(ROOT).enumerate_campaign(
        WorkbenchEnumerationRequest(
            campaign_id="C0045", maximum_realizations=2, maximum_search_states=1000
        )
    )
    path = tmp_path / "C0045.realization-space.json"
    path.write_text(response.model_dump_json(indent=2))
    return path


def test_export_can_be_recomputed_from_another_working_directory(
    tmp_path: Path,
    exported_result: Path,
) -> None:
    output = tmp_path / "recomputed.json"
    completed = run_cli(
        "--from-result", str(exported_result), "--output", str(output), cwd=tmp_path
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text()) == json.loads(exported_result.read_text())
    assert json.loads(output.read_text())["result"]["operational_status"] == "not_run"


def test_modified_export_is_rejected_without_writing_an_output(
    tmp_path: Path,
    exported_result: Path,
) -> None:
    payload = json.loads(exported_result.read_text())
    payload["request"]["maximum_realizations"] = 3
    exported_result.write_text(json.dumps(payload))
    output = tmp_path / "should-not-exist.json"
    completed = run_cli(
        "--from-result", str(exported_result), "--output", str(output), cwd=tmp_path
    )
    assert completed.returncode != 0
    assert not output.exists()


def test_plain_request_uses_the_same_bounded_enumerator(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "campaign_id": "C0045",
                "maximum_realizations": 2,
                "maximum_search_states": 1000,
            }
        )
    )
    output = tmp_path / "result.json"
    completed = run_cli(
        "--request", str(request), "--output", str(output), cwd=tmp_path
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text())
    assert result["request"]["maximum_realizations"] == 2
    assert result["result"]["realization_count"] == 2
    assert result["result"]["operational_status"] == "not_run"


def test_unavailable_campaign_is_explicitly_rejected(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_text('{"campaign_id":"C0001"}')
    output = tmp_path / "result.json"
    completed = run_cli(
        "--request", str(request), "--output", str(output), cwd=tmp_path
    )
    assert completed.returncode != 0
    assert "not enumeration-ready" in completed.stderr
    assert not output.exists()


def test_existing_output_is_preserved(tmp_path: Path, exported_result: Path) -> None:
    output = tmp_path / "existing.json"
    output.write_text("preserve this evidence")
    completed = run_cli(
        "--from-result", str(exported_result), "--output", str(output), cwd=tmp_path
    )
    assert completed.returncode != 0
    assert output.read_text() == "preserve this evidence"


def test_output_is_required_for_cli_mode(tmp_path: Path, exported_result: Path) -> None:
    completed = run_cli("--from-result", str(exported_result), cwd=tmp_path)
    assert completed.returncode == 2
