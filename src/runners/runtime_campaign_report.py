"""Explicit campaign outcomes separate executor returns, simulation and effects."""

import json
from pathlib import Path
from typing import Literal, Self

from pydantic import computed_field, model_validator

from runners.capability_facts import (
    CapabilityFact,
    Identity,
    ImmutableRecord,
    ObservationReference,
)
from runners.capability_observations import _directory, _write_exclusive
from runners.lab_runtime_bootstrap import LabBootstrapOutcome, LabTopologyWitness
from runners.runtime_invocation import RuntimeOccurrenceOutcome
from runners.runtime_journal import RuntimeJournalReference
from runners.runtime_step_contracts import RuntimeStepContract
from runners.runtime_diagnostics import ProcessFailure


class RuntimeCampaignStep(ImmutableRecord):
    contract: RuntimeStepContract
    status: Literal["not_run", "simulated", "observed", "failed", "blocked", "error"]
    outcome: RuntimeOccurrenceOutcome | None
    error_type: str | None = None
    error_message: str | None = None
    process_failure: ProcessFailure | None = None
    revalidation_references: tuple[ObservationReference, ...] = ()

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status in {"observed", "simulated", "failed"} and self.outcome is None:
            raise ValueError("An evaluated step requires its retained outcome")
        if self.status == "observed" and (
            self.contract.mode == "naive_simulated"
            or not self.outcome.invocation.executor_completed
            or not self.outcome.observations
            or not all(item.passed for item in self.outcome.observations)
            or len(self.outcome.observation_references)
            != len(self.outcome.observations)
        ):
            raise ValueError(
                "Observed status requires successful independent observations"
            )
        if self.status == "simulated" and (
            self.contract.mode != "naive_simulated"
            or not self.outcome.invocation.executor_completed
            or self.outcome.authorizing_facts
            or self.outcome.observations
        ):
            raise ValueError("Simulation status cannot report controlled authority")
        if self.status in {"blocked", "error"} and (
            self.error_type is None or self.error_message is None
        ):
            raise ValueError("Blocked and error states require the original diagnostic")
        if self.status == "not_run" and self.outcome is not None:
            raise ValueError("A pending step cannot contain an invocation outcome")
        return self


class RuntimeCampaignReport(ImmutableRecord):
    schema_version: Literal["runtime-campaign/v2"]
    campaign_id: Identity
    run_id: Identity
    infrastructure_provider: str
    bootstrap: LabBootstrapOutcome | None
    topology: LabTopologyWitness | None = None
    steps: tuple[RuntimeCampaignStep, ...]
    runtime_facts: tuple[CapabilityFact, ...]
    journal_references: tuple[RuntimeJournalReference, ...]
    error_type: str | None = None
    error_message: str | None = None
    process_failure: ProcessFailure | None = None

    @model_validator(mode="after")
    def validate_occurrence_scope(self) -> Self:
        occurrences = set()
        for step in self.steps:
            if step.contract.campaign_id != self.campaign_id:
                raise ValueError("Occurrence belongs to another campaign")
            if step.contract.scope.run_id != self.run_id:
                raise ValueError("Occurrence belongs to another run")
            if step.contract.occurrence in occurrences:
                raise ValueError("Report contains a duplicate occurrence")
            occurrences.add(step.contract.occurrence)
        return self

    @computed_field
    @property
    def total_techniques(self) -> int:
        return len(self.steps)

    @computed_field
    @property
    def effects_observed(self) -> int:
        return sum(step.status == "observed" for step in self.steps)

    @computed_field
    @property
    def simulated(self) -> int:
        return sum(step.status == "simulated" for step in self.steps)

    @computed_field
    @property
    def failed(self) -> int:
        return sum(step.status not in {"observed", "simulated"} for step in self.steps)


def parse_retained_campaign_report(content: str) -> RuntimeCampaignReport:
    """Parse a retained report and reject inconsistent computed counters."""
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("Campaign report must be a JSON object")
    counters = ("total_techniques", "effects_observed", "simulated", "failed")
    retained_counters = {}
    for name in counters:
        value = payload.pop(name, None)
        if type(value) is not int:
            raise ValueError(f"Retained campaign report lacks integer {name}")
        retained_counters[name] = value
    report = RuntimeCampaignReport.model_validate(payload)
    for name, retained_value in retained_counters.items():
        if retained_value != getattr(report, name):
            raise ValueError(f"Retained campaign report has inconsistent {name}")
    return report


def retain_campaign_report(
    report: RuntimeCampaignReport, *, run_root: Path, filename: str
) -> None:
    """Write one new plan or final report without replacing an earlier run."""
    if filename not in {"plan.json", "summary.json"}:
        raise ValueError("Campaign reports require a fixed plan or summary filename")
    content = report.model_dump_json(indent=2).encode("utf-8")
    with _directory(None, str(run_root)) as directory:
        _write_exclusive(directory, filename, content)
