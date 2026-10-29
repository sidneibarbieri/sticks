from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ARTIFACT_ROOT = Path(__file__).resolve().parents[1]


def _snapshot_registry_bindings() -> dict:
    script = """
import json
import sys
from pathlib import Path

artifact_root = Path.cwd()
sys.path.insert(0, str(artifact_root / "src"))

from executors.registry_initializer import initialize_registry
from executors.executor_registry import registry

initialize_registry(force=True)

snapshot = {}
for technique_id in ("T1016", "T1059.006", "T1190", "T1546.004", "T1068"):
    executor = registry.get_executor(technique_id, "0.shadowray")
    metadata = registry.get_metadata(technique_id, "0.shadowray")
    snapshot[technique_id] = {
        "executor_module": executor.__module__ if executor else None,
        "executor_name": executor.__name__ if executor else None,
        "produces": list(metadata.produces) if metadata else [],
        "requires": list(metadata.requires) if metadata else [],
    }

print(json.dumps(snapshot))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ARTIFACT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_t1016_binding_prefers_shadowray_fixed_executor() -> None:
    snapshot = _snapshot_registry_bindings()
    t1016 = snapshot["T1016"]
    assert t1016["executor_module"] == "executors.shadowray_fixed_executors"
    assert t1016["executor_name"] == "execute_t1016_shadowray_fixed"


def test_shadowray_startup_and_persistence_bind_to_guest_transport() -> None:
    snapshot = _snapshot_registry_bindings()

    assert snapshot["T1059.006"]["executor_module"] == (
        "executors.shadowray_fixed_executors"
    )
    assert snapshot["T1059.006"]["executor_name"] == "execute_t1059_006_shadowray_vm"
    assert snapshot["T1546.004"]["executor_module"] == (
        "executors.shadowray_fixed_executors"
    )
    assert snapshot["T1546.004"]["executor_name"] == (
        "execute_t1546_004_shadowray_vm"
    )


def test_t1190_metadata_records_http_observation_without_initial_access() -> None:
    snapshot = _snapshot_registry_bindings()
    assert snapshot["T1190"]["produces"] == ["observation:ray_api_http"]
    campaign = json.loads(
        (ARTIFACT_ROOT / "campaigns/0.shadowray.json").read_text(encoding="utf-8")
    )
    first_step = campaign["techniques"][0]
    assert first_step["technique_id"] == "T1190"
    assert first_step["produces"] == snapshot["T1190"]["produces"]


def test_legacy_shadowray_import_cannot_replace_selected_executors() -> None:
    script = """
from executors import shadowray_fixed_executors
from executors.executor_registry import registry

techniques = (
    "T1190", "T1003.008", "T1016", "T1059.006", "T1027.013",
    "T1105", "T1496.001", "T1546.004", "T1588.002",
)
before = {
    technique_id: registry.get_executor(technique_id, "0.shadowray")
    for technique_id in techniques
}
from executors import shadowray_additional_executors
after = {
    technique_id: registry.get_executor(technique_id, "0.shadowray")
    for technique_id in techniques
}
assert before == after
assert all(executor.__module__ == "executors.shadowray_fixed_executors" for executor in after.values())
"""
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=ARTIFACT_ROOT,
        env=dict(os.environ, PYTHONPATH=str(ARTIFACT_ROOT / "src")),
        check=True,
        capture_output=True,
        text=True,
    )


def test_t1068_metadata_requires_initial_access_capability() -> None:
    snapshot = _snapshot_registry_bindings()
    assert "access:initial" in snapshot["T1068"]["requires"]


def test_shadowray_toolkit_does_not_run_for_c0010(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(ARTIFACT_ROOT / "src"))
    from executors import shadowray_fixed_executors

    calls: list[str] = []

    def generic_executor(campaign_id: str, sut_profile_id: str, **kwargs):
        calls.append(campaign_id)
        return True, "generic", "", []

    def shadowray_executor(campaign_id: str, sut_profile_id: str, **kwargs):
        calls.append("shadowray")
        return True, "shadowray", "", []

    monkeypatch.setattr(shadowray_fixed_executors, "execute_t1588_002_real", generic_executor)
    monkeypatch.setattr(
        shadowray_fixed_executors, "execute_t1588_002_shadowray_vm", shadowray_executor
    )

    c0010_result = shadowray_fixed_executors.execute_t1588_002_shadowray_fixed(
        "0.c0010", "0.c0010"
    )
    shadowray_result = shadowray_fixed_executors.execute_t1588_002_shadowray_fixed(
        "0.shadowray", "0.shadowray"
    )

    assert c0010_result[1] == "generic"
    assert shadowray_result[1] == "shadowray"
    assert calls == ["0.c0010", "shadowray"]


def test_shared_techniques_select_generic_procedures_outside_shadowray() -> None:
    script = """
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))
from executors.registry_initializer import initialize_registry
from executors.executor_registry import registry
initialize_registry(force=True)
techniques = ("T1016", "T1059.006", "T1105", "T1190", "T1588.002", "T1027.013")
print(json.dumps({technique: {
    campaign: (executor.__module__, executor.__name__) if executor else None
    for campaign in ("0.shadowray", "0.c0010")
    for executor in (registry.get_executor(technique, campaign),)
} for technique in techniques}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ARTIFACT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    bindings = json.loads(completed.stdout)
    for technique_id, campaigns in bindings.items():
        assert campaigns["0.shadowray"][0] == "executors.shadowray_fixed_executors"
        assert campaigns["0.c0010"] is not None, technique_id
        assert campaigns["0.c0010"][0] != "executors.shadowray_fixed_executors"
