"""The workbench's STIX-bundle panel and scripts/emulate.py share one admission service."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.bundle_admission import (  # noqa: E402
    BundleAdmissionError,
    BundleAdmissionResult,
    admit_campaign,
)
from concretization.workbench import RealizationWorkbench  # noqa: E402
from concretization.workbench_http import build_handler  # noqa: E402

BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"


@pytest.fixture(scope="module")
def server():
    workbench = RealizationWorkbench(PROJECT_ROOT)
    httpd = HTTPServer(("127.0.0.1", 0), build_handler(workbench, PROJECT_ROOT / "web" / "realization-workbench"))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def _post(url: str, body: bytes, origin: str | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    if origin is not None:
        request.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_http_admission_equals_cli_json(server: str, tmp_path: Path) -> None:
    output = tmp_path / "C0045.admission.json"
    completed = subprocess.run(
        [sys.executable, "scripts/emulate.py", "C0045", "--json-output", str(output)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600,
    )
    assert completed.returncode == 0, completed.stderr
    status, payload = _post(f"{server}/api/bundle-admission?campaign=C0045", BUNDLE.read_bytes())
    assert status == 200
    assert payload == json.loads(output.read_text(encoding="utf-8"))
    result = BundleAdmissionResult.model_validate(payload)
    assert len(result.admitted_steps) == result.plan_step_count == 10
    assert result.operational_status == "not_run"


def test_unsupported_steps_are_reported_not_invented(tmp_path: Path) -> None:
    _, _, result = admit_campaign(PROJECT_ROOT, "C0001", BUNDLE, tmp_path)
    assert result.unresolved_technique_ids
    assert len(result.admitted_steps) + len(result.unresolved_technique_ids) <= result.plan_step_count


@pytest.mark.parametrize("campaign", ["../../etc", "", "C 0045", "x" * 65])
def test_campaign_identifier_is_validated(campaign: str, tmp_path: Path) -> None:
    with pytest.raises(BundleAdmissionError):
        admit_campaign(PROJECT_ROOT, campaign, BUNDLE, tmp_path)


def test_rejects_non_bundle_unknown_campaign_and_cross_origin(server: str) -> None:
    status, payload = _post(f"{server}/api/bundle-admission?campaign=C0045", b'{"type": "indicator"}')
    assert (status, payload["error"]) == (400, "invalid_bundle")
    status, payload = _post(f"{server}/api/bundle-admission?campaign=C0045", b"not json")
    assert (status, payload["error"]) == (400, "invalid_bundle")
    status, payload = _post(f"{server}/api/bundle-admission?campaign=C9999", BUNDLE.read_bytes())
    assert (status, payload["error"]) == (422, "admission_rejected")
    status, payload = _post(f"{server}/api/bundle-admission?campaign=C0045", b"{}", origin="http://example.org")
    assert (status, payload["error"]) == (403, "cross_origin_rejected")


def test_cli_reports_unknown_campaign_without_traceback() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/emulate.py", "C9999"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600,
    )
    assert completed.returncode == 2
    assert completed.stderr.startswith("error: Campaign C9999")
    assert "Traceback" not in completed.stderr


def test_bundle_panel_is_served_and_fails_closed_from_file_urls() -> None:
    web_root = PROJECT_ROOT / "web" / "realization-workbench"
    index = (web_root / "index.html").read_text(encoding="utf-8")
    script = (web_root / "bundle.js").read_text(encoding="utf-8")
    assert 'src="bundle.js"' in index
    assert 'window.location.protocol === "file:"' in script
