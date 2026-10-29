"""Loaded campaign expectations must agree with the selected executor contract."""

import json
from pathlib import Path

import pytest

from executors.executor_registry import registry
from executors import legacy_parity_expansion_executors as legacy_executors
from executors.registry_initializer import initialize_registry
from loaders.campaign_loader import load_campaign, load_sut_profile


@pytest.mark.parametrize("campaign_id", [
    "0.apt41_dust", "0.c0010", "0.c0026", "0.costaricto",
    "0.operation_midnighteclipse", "0.outer_space",
    "0.salesforce_data_exfiltration", "0.shadowray",
])
def test_loaded_expectations_do_not_promote_simulated_executor_contracts(campaign_id):
    initialize_registry()
    campaign = load_campaign(campaign_id)
    mismatches = []
    for step in campaign.steps:
        metadata = registry.get_metadata(step.technique_id, campaign_id)
        assert metadata is not None
        expected = (step.expected_mode.value, step.expected_fidelity.value)
        selected = (metadata.execution_mode.value, metadata.execution_fidelity.value)
        if expected != selected:
            mismatches.append((step.technique_id, expected, selected))
    assert not mismatches, mismatches


def test_apt41_encoded_file_profile_does_not_promise_adapted_execution():
    profile = load_sut_profile("0.apt41_dust")
    assert profile.fidelity_expectations["T1027.013"].value == "inspired"


def test_outer_space_simulations_do_not_publish_operational_capabilities():
    initialize_registry()
    campaign = load_campaign("0.outer_space")
    for step in campaign.steps:
        if step.expected_mode.value != "naive_simulated":
            continue
        metadata = registry.get_metadata(step.technique_id, campaign.campaign_id)
        assert metadata is not None
        assert metadata.produces
        assert all(product.startswith("simulation:") for product in metadata.produces), (
            step.technique_id,
            metadata.produces,
        )


def test_apt41_simulations_publish_records_only():
    initialize_registry()
    campaign = load_campaign("0.apt41_dust")
    for step in campaign.steps:
        if step.expected_mode.value != "naive_simulated":
            continue
        metadata = registry.get_metadata(step.technique_id, campaign.campaign_id)
        assert metadata is not None
        assert metadata.produces
        assert all(product.startswith("simulation:") for product in metadata.produces), (
            step.technique_id,
            metadata.produces,
        )

    search = registry.get_metadata("T1593.002", campaign.campaign_id)
    website = registry.get_metadata("T1594", campaign.campaign_id)
    assert search is not None and website is not None
    assert website.requires == search.produces


@pytest.mark.parametrize("campaign_id", [
    "0.costaricto",
    "0.operation_midnighteclipse",
    "0.salesforce_data_exfiltration",
])
def test_remaining_historical_simulations_publish_records_only(campaign_id):
    initialize_registry()
    campaign = load_campaign(campaign_id)
    for step in campaign.steps:
        metadata = registry.get_metadata(step.technique_id, campaign_id)
        assert metadata is not None
        if metadata.execution_mode.value != "naive_simulated":
            continue
        assert metadata.produces
        assert all(product.startswith("simulation:") for product in metadata.produces), (
            step.technique_id,
            metadata.produces,
        )


@pytest.mark.parametrize("campaign_id,technique_id", [
    ("0.costaricto", "T1090.003"),
    ("0.operation_midnighteclipse", "T1003.003"),
    ("0.salesforce_data_exfiltration", "T1090"),
])
def test_legacy_simulation_outputs_are_labeled_records(
    monkeypatch, tmp_path, campaign_id, technique_id,
):
    initialize_registry()
    campaign_dir = tmp_path / campaign_id
    campaign_dir.mkdir()
    monkeypatch.setattr(legacy_executors, "_campaign_dir", lambda _campaign: campaign_dir)

    result = registry.get_executor(technique_id, campaign_id)(campaign_id, campaign_id)

    assert result[0] and not result[2]
    artifacts = [Path(path) for path in result[3]]
    assert artifacts and all(artifact.is_file() for artifact in artifacts)
    records = [artifact for artifact in artifacts if artifact.suffix == ".json"]
    assert len(records) == 1
    assert json.loads(records[0].read_text())["evidence_kind"] == "simulation_record"


@pytest.mark.parametrize("technique_id", ["T1053.005", "T1133", "T1572"])
def test_costaricto_configuration_simulations_write_local_artifacts(
    monkeypatch, tmp_path, technique_id,
):
    initialize_registry()
    monkeypatch.chdir(tmp_path)

    result = registry.get_executor(technique_id, "0.costaricto")(
        "0.costaricto", "0.costaricto",
    )

    assert result[0] and not result[2]
    assert len(result[3]) == 1
    assert Path(result[3][0]).is_file()
