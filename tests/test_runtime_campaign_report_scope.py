"""A retained campaign report cannot mix occurrence identities."""

import pytest
from pydantic import ValidationError

from runners.capability_facts import FactScope
from runners.runtime_campaign_report import RuntimeCampaignReport, RuntimeCampaignStep
from runners.runtime_step_contracts import RuntimeStepContract


def pending_step(*, campaign_id: str = "0.c0010", run_id: str = "run-a") -> RuntimeCampaignStep:
    scope = FactScope(
        run_id=run_id,
        environment_id="lab-a",
        epoch="boot-a",
        locus="controller",
        host_id="controller",
        principal=None,
    )
    contract = RuntimeStepContract(
        campaign_id=campaign_id,
        occurrence=1,
        technique_id="T1584.001",
        executor_id="executors.example.execute",
        executor_sha256="a" * 64,
        mode="naive_simulated",
        scope=scope,
        requirements=(),
        observers=(),
    )
    return RuntimeCampaignStep(contract=contract, status="not_run", outcome=None)


def report_with(*steps: RuntimeCampaignStep) -> RuntimeCampaignReport:
    return RuntimeCampaignReport(
        schema_version="runtime-campaign/v2",
        campaign_id="0.c0010",
        run_id="run-a",
        infrastructure_provider="qemu",
        bootstrap=None,
        steps=steps,
        runtime_facts=(),
        journal_references=(),
    )


def test_report_rejects_occurrence_from_another_campaign() -> None:
    with pytest.raises(ValidationError, match="campaign"):
        report_with(pending_step(campaign_id="0.c0026"))


def test_report_rejects_occurrence_from_another_run() -> None:
    with pytest.raises(ValidationError, match="run"):
        report_with(pending_step(run_id="run-b"))


def test_report_rejects_duplicate_occurrence() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        report_with(pending_step(), pending_step())
