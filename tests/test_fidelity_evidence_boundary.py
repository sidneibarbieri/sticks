"""Executor declarations must not masquerade as verified fidelity."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from executors import models as execution_models
import models as domain_models
from runners import campaign_runner


@pytest.mark.parametrize("model_module", [execution_models, domain_models])
def test_loading_legacy_summary_does_not_assign_new_distribution_basis(model_module):
    campaign = model_module.CampaignEvidence.model_validate({
        "campaign_id": "fixture", "sut_profile_id": "fixture",
        "start_time": datetime.now().isoformat(),
        "fidelity_distribution": {"faithful": 1},
    })
    assert campaign.fidelity_distribution_basis is None
    assert campaign.fidelity_distribution == {"faithful": 1}


@pytest.mark.parametrize("model_module", [execution_models, domain_models])
def test_new_assessment_has_no_automatic_verification(model_module):
    assessment = model_module.FidelityAssessment(
        declared="adapted", justification="Declared fixture behavior"
    )
    assert assessment.verified is None


@pytest.mark.parametrize("model_module", [execution_models, domain_models])
def test_summary_counts_declarations_not_legacy_verification(model_module):
    assessment = model_module.FidelityAssessment(
        declared="inspired", verified="faithful", justification="Legacy label"
    )
    technique = model_module.TechniqueEvidence(
        technique_id="T1068", status="success", execution_mode="naive_simulated",
        fidelity=assessment, start_time=datetime.now(), end_time=datetime.now(),
    )
    campaign = model_module.CampaignEvidence(
        campaign_id="fixture", sut_profile_id="fixture", start_time=datetime.now(),
        technique_results=[technique],
    )
    campaign.compute_summary()
    assert campaign.fidelity_distribution == {"inspired": 1}
    assert campaign.fidelity_distribution_basis == "declared"
    assert assessment.verified.value == "faithful"


@pytest.mark.parametrize("executor_status", ["success", "failed"])
def test_runner_does_not_verify_executor_declaration(monkeypatch, executor_status):
    runner = campaign_runner.UnifiedCampaignRunner.__new__(
        campaign_runner.UnifiedCampaignRunner
    )
    runner._infrastructure_provider = ""
    runner.accumulated_capabilities = set()
    runner.campaign = SimpleNamespace(campaign_id="fixture")
    runner.sut = SimpleNamespace(campaign_id="fixture")
    step = SimpleNamespace(
        technique_id="T1068", technique_name="Fixture", sut_delta=None
    )
    raw_evidence = SimpleNamespace(
        status=executor_status, executor_name="tests.fixture_executor", execution_fidelity="inspired",
        fidelity_justification="Synthetic fixture", execution_mode="naive_simulated",
        artifacts_created=[], prerequisites_consumed=[], capabilities_produced=[],
        stdout="", stderr="",
    )
    monkeypatch.setattr(
        campaign_runner, "execute_technique", lambda **arguments: raw_evidence
    )
    monkeypatch.setattr(
        campaign_runner.registry, "get_metadata", lambda technique, campaign_id=None: None
    )

    evidence = runner._execute_step(step)

    assert evidence.status == executor_status
    assert evidence.fidelity.declared.value == "inspired"
    assert evidence.fidelity.verified is None


def test_failed_step_does_not_verify_expected_fidelity():
    runner = campaign_runner.UnifiedCampaignRunner.__new__(
        campaign_runner.UnifiedCampaignRunner
    )
    step = SimpleNamespace(
        technique_id="T1068", technique_name="Fixture",
        expected_mode="naive_simulated", expected_fidelity="inspired",
    )

    evidence = runner._make_skipped_evidence(step, datetime.now(), "Fixture failure")

    assert evidence.status == "failed"
    assert evidence.fidelity.verified is None
