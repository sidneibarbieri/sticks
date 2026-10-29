"""Simulated privilege artifacts cannot establish real privileged authority."""

import json
from pathlib import Path

import pytest

from executors import privilege_escalation_executors as privilege
from executors.executor_registry import execute_technique, registry


def test_shadowray_manifest_does_not_claim_privileged_authority():
    campaign_path = Path(__file__).resolve().parents[1] / "campaigns/0.shadowray.json"
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    escalation = next(
        step for step in campaign["techniques"] if step["technique_id"] == "T1068"
    )
    assert escalation["expected_mode"] == "naive_simulated"
    assert escalation["produces"] == privilege.metadata_t1068.produces


def test_simulation_metadata_does_not_grant_privileged_authority():
    assert privilege.metadata_t1068.produces == [
        "simulation:privilege_escalation_recorded"
    ]


def test_simulation_output_disclaims_real_escalation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    success, stdout, stderr, artifacts = privilege.execute_t1068_inspired(
        "0.shadowray", "0.shadowray"
    )
    assert success
    assert not stderr
    assert "No privilege escalation was performed" in stdout
    assert "No root shell was established" in Path(artifacts[1]).read_text()


def test_execution_evidence_retains_simulation_boundary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    monkeypatch.setitem(registry._executors, "T1068", privilege.execute_t1068_inspired)
    monkeypatch.setitem(registry._metadata, "T1068", privilege.metadata_t1068)
    monkeypatch.setattr(registry, "_evidence_dir", None)
    evidence = execute_technique(
        "T1068", ["access:initial"], "0.shadowray", "0.shadowray"
    )
    assert evidence.status == "success"
    assert evidence.execution_mode == "naive_simulated"
    assert evidence.execution_fidelity == "inspired"
    assert evidence.capabilities_produced == [
        "simulation:privilege_escalation_recorded"
    ]
    assert "system:root_access" not in evidence.capabilities_produced
    assert "access:privileged" not in evidence.capabilities_produced


def test_unexpected_write_failure_is_visible(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)

    def deny_write(*args, **kwargs):
        raise PermissionError("fixture write denied")

    monkeypatch.setattr(Path, "write_text", deny_write)
    with pytest.raises(PermissionError, match="fixture write denied"):
        privilege.execute_t1068_inspired("0.shadowray", "0.shadowray")
