"""Manifest creation does not establish authentication or a delivery endpoint."""

import json
from pathlib import Path

import yaml

import pytest

from executors import legacy_parity_expansion_executors as executors
from executors.executor_registry import ExecutionMode, registry
from executors.registry_initializer import initialize_registry
from loaders.campaign_loader import load_campaign


@pytest.mark.parametrize("campaign,technique,simulated_fact,unobserved_fact", [
    ("0.operation_midnighteclipse", "T1078", "simulation:valid_account_recorded", "access:initial"),
    ("0.salesforce_data_exfiltration", "T1608.005", "simulation:delivery_link_recorded", "resources:delivery_link"),
])
def test_manifest_only_handlers_do_not_assert_external_effects(
    monkeypatch, tmp_path, campaign, technique, simulated_fact, unobserved_fact,
):
    initialize_registry(force=True)
    monkeypatch.setattr(executors, "_campaign_dir", lambda campaign: tmp_path)
    metadata = registry.get_metadata(technique, campaign)
    assert metadata.execution_mode is ExecutionMode.NAIVE_SIMULATED
    assert metadata.produces == [simulated_fact]
    assert unobserved_fact not in metadata.produces
    result = registry.get_executor(technique, campaign)(campaign, campaign)
    assert result[0] is True
    record = json.loads((tmp_path / (technique.replace(".", "_").lower() + "_manifest.json")).read_text())
    assert record["evidence_kind"] == "simulation_record"


@pytest.mark.parametrize("campaign,technique", [
    ("0.operation_midnighteclipse", "T1078"),
    ("0.operation_midnighteclipse", "T1588.002"),
    ("0.salesforce_data_exfiltration", "T1608.005"),
    ("0.salesforce_data_exfiltration", "T1588.002"),
])
def test_declared_campaign_and_profile_match_record_only_behavior(campaign, technique):
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / "campaigns" / (campaign + ".json")).read_text())
    step = next(step for step in plan["techniques"] if step["technique_id"] == technique)
    profile = yaml.safe_load((root / "data/sut_profiles" / (campaign + ".yml")).read_text())
    assert step.get("expected_mode") == "naive_simulated"
    assert step["expected_fidelity"] == "inspired"
    assert profile["fidelity_expectations"][technique] == "INSPIRED"


def test_manifest_helper_rejects_controlled_execution_classification(monkeypatch):
    from executors.executor_registry import ExecutorRegistry, ExecutionFidelity
    isolated_registry = ExecutorRegistry()
    monkeypatch.setattr(executors, "registry", isolated_registry)
    spec = executors.ManifestExecutorSpec(
        technique_id="T9999", technique_name="Synthetic test record",
        execution_mode=ExecutionMode.REAL_CONTROLLED,
        execution_fidelity=ExecutionFidelity.ADAPTED,
        produces=["access:initial"], requires=[], description="Record only",
        fidelity_justification="No observed authentication", original_platform="any",
    )
    with pytest.raises(ValueError, match="Manifest-only"):
        executors._register_manifest_executor(spec)
    assert isolated_registry.get_executor("T9999") is None


@pytest.mark.parametrize("products", [[], ["access:initial"]])
def test_manifest_helper_rejects_unscoped_or_empty_products(monkeypatch, products):
    from executors.executor_registry import ExecutorRegistry, ExecutionFidelity

    isolated_registry = ExecutorRegistry()
    monkeypatch.setattr(executors, "registry", isolated_registry)
    spec = executors.ManifestExecutorSpec(
        technique_id="T9999",
        technique_name="Synthetic test record",
        execution_mode=ExecutionMode.NAIVE_SIMULATED,
        execution_fidelity=ExecutionFidelity.INSPIRED,
        produces=products,
        requires=[],
        description="Record only",
        fidelity_justification="No observed effect",
        original_platform="any",
    )

    with pytest.raises(ValueError, match="simulation records"):
        executors._register_manifest_executor(spec)
    assert isolated_registry.get_executor("T9999") is None


@pytest.mark.parametrize("campaign_id", [
    "0.apt41_dust",
    "0.operation_midnighteclipse",
    "0.salesforce_data_exfiltration",
])
def test_selected_manifest_steps_emit_simulation_records(
    monkeypatch, tmp_path, campaign_id,
):
    initialize_registry(force=True)
    monkeypatch.setattr(executors, "_campaign_dir", lambda _campaign: tmp_path)
    campaign = load_campaign(campaign_id)

    for step in campaign.steps:
        executor = registry.get_executor(step.technique_id, campaign_id)
        if executor.__name__ != "execute_manifest":
            continue
        metadata = registry.get_metadata(step.technique_id, campaign_id)
        assert all(product.startswith("simulation:") for product in metadata.produces)
        success, _message, error, artifacts = executor(campaign_id, campaign_id)
        assert success and not error
        assert len(artifacts) == 1
        assert json.loads(Path(artifacts[0]).read_text())["evidence_kind"] == "simulation_record"
