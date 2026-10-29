"""C0010 simulated steps cannot publish operational capabilities."""

import json
from pathlib import Path

import pytest

from executors import executor_registry, legacy_campaign_executors
from executors.executor_registry import execute_technique


CAMPAIGN_PATH = Path(__file__).resolve().parents[1] / "campaigns" / "0.c0010.json"
SIMULATED_TECHNIQUES = ["T1584.001", "T1587.001", "T1583.001", "T1588.002"]


@pytest.mark.parametrize("technique_id", SIMULATED_TECHNIQUES)
def test_manifest_only_step_preserves_simulation_origin(
    technique_id, monkeypatch, tmp_path
):
    """A local manifest or malware specification is not an acquired effect."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(legacy_campaign_executors, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path / "artifacts")

    evidence = execute_technique(
        technique_id=technique_id,
        available_capabilities=["resources:staging_directory"],
        campaign_id="0.c0010",
        sut_profile_id="0.c0010",
    )

    assert evidence.status == "success"
    assert evidence.capabilities_produced
    assert all(
        capability.startswith("simulation:")
        for capability in evidence.capabilities_produced
    )


def test_campaign_products_match_simulated_executor_products():
    """The runner's declarations must agree with the emitted evidence."""
    campaign = json.loads(CAMPAIGN_PATH.read_text(encoding="utf-8"))
    declared = {
        technique["technique_id"]: technique["produces"]
        for technique in campaign["techniques"]
    }
    from executors.executor_registry import registry

    for technique_id in SIMULATED_TECHNIQUES:
        metadata = registry.get_metadata(technique_id, "0.c0010")
        assert metadata is not None
        assert declared[technique_id] == metadata.produces


def test_compromised_domain_manifest_uses_reserved_namespace(monkeypatch, tmp_path):
    """A simulated takeover must not name an operational domain."""
    monkeypatch.setattr(legacy_campaign_executors, "ARTIFACTS_DIR", tmp_path)

    completed, _, _, products = (
        legacy_campaign_executors.execute_t1584_001_simulated(
            campaign_id="0.c0010",
            sut_profile_id="0.c0010",
        )
    )

    assert completed
    assert len(products) == 1
    manifest = json.loads(Path(products[0]).read_text(encoding="utf-8"))
    assert manifest["domain"] == "oldsub.shipping.example"
