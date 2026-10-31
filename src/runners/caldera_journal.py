"""Verify retained CALDERA identity, coverage and target-boot consistency."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from adapters.caldera_command_result import CalderaCommandResult
from runners.caldera_campaign_support import SUPPORTED_CALDERA_CAMPAIGNS
from runners.caldera_occurrence_binding import CalderaOccurrenceBinding
from runners.caldera_session import CalderaSession
from runners.c0045_full_runtime_contracts import c0045_native_occurrences
from runners.capability_facts import ImmutableRecord
from runners.recorded_caldera_dispatch import replay_completed_command
from runners.runtime_campaign_report import (
    RuntimeCampaignReport,
    RuntimeCampaignStep,
    parse_retained_campaign_report,
)

Count = Annotated[int, Field(strict=True, ge=0)]
SESSION_IDENTITY_FIELDS = (
    "operation_id", "group", "agent_id", "host", "principal", "platform", "executor",
)
ASSURANCE_SCOPE = (
    "Retained journal consistency and boot binding; not native-server replay or historical fidelity"
)


class CalderaJournalVerification(ImmutableRecord):
    schema_version: Literal["caldera-journal-consistency/v1"] = Field(
        default="caldera-journal-consistency/v1", alias="schema"
    )
    commands: Count
    observed: Count
    simulated: Count
    observed_target: Count
    observed_controller: Count
    scope: str = ASSURANCE_SCOPE

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        if self.commands == 0 or self.commands != self.observed_target:
            raise ValueError("Native command count differs from observed target occurrence count")
        if self.observed != self.observed_target + self.observed_controller:
            raise ValueError("Observed occurrence has no reviewed execution locus")
        return self



class CalderaJournalVerificationV2(ImmutableRecord):
    schema_version: Literal["caldera-journal-consistency/v2"] = Field(
        default="caldera-journal-consistency/v2", alias="schema"
    )
    commands: Count
    observed: Count
    simulated: Count
    observed_target: Count
    observed_controller: Count
    simulated_target_commands: Count
    scope: str = ASSURANCE_SCOPE

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        if self.commands == 0 or self.commands != self.observed_target + self.simulated_target_commands:
            raise ValueError("Native commands differ from observed and simulated target occurrences")
        if self.simulated_target_commands > self.simulated:
            raise ValueError("Native simulations exceed all simulated occurrences")
        if self.observed != self.observed_target + self.observed_controller:
            raise ValueError("Observed occurrence has no reviewed execution locus")
        return self


def _read_campaign_report(evidence: Path) -> RuntimeCampaignReport:
    reports = tuple((evidence / "runtime-v2").glob("*/summary.json"))
    if len(reports) != 1:
        raise ValueError("Expected exactly one runtime campaign report")
    report = parse_retained_campaign_report(reports[0].read_text())
    if report.campaign_id not in SUPPORTED_CALDERA_CAMPAIGNS:
        raise ValueError("Campaign has no reviewed CALDERA journal scope")
    if any(step.status not in {"observed", "simulated"} for step in report.steps):
        raise ValueError("Campaign contains an incomplete or failed occurrence")
    return report


def _verify_dispatches(
    evidence: Path, session: CalderaSession,
) -> tuple[CalderaCommandResult, ...]:
    directories = sorted((evidence / "caldera-dispatch").glob("command-*"))
    if not directories:
        raise ValueError("No retained CALDERA commands")
    results = tuple(replay_completed_command(directory) for directory in directories)
    links: set[str] = set()
    for result in results:
        dispatch = result.dispatch
        for field in SESSION_IDENTITY_FIELDS:
            if getattr(dispatch, field) != getattr(session.binding, field):
                raise ValueError("Retained command differs from session: " + field)
        if dispatch.link_id in links:
            raise ValueError("Repeated CALDERA link identity")
        links.add(dispatch.link_id)
    return results


def _verify_target_observations(
    steps: tuple[RuntimeCampaignStep, ...], session: CalderaSession,
) -> None:
    for step in steps:
        if step.outcome is None or not step.outcome.observations:
            raise ValueError("Observed occurrence has no predicate observations")
        for observation in step.outcome.observations:
            if (
                not observation.passed
                or observation.scope.epoch != str(session.target_boot_id)
                or observation.scope.host_id != session.binding.host
            ):
                raise ValueError("Observation differs from the session target boot")



def verify_occurrence_bindings(
    evidence: Path, report: RuntimeCampaignReport,
    results: tuple[CalderaCommandResult, ...],
) -> None:
    directories = sorted((evidence / "caldera-dispatch").glob("command-*"))
    binding_paths = tuple(directory / "occurrence-binding.json" for directory in directories)
    if report.campaign_id != "0.shadowray" and not any(path.exists() for path in binding_paths):
        return
    if len(binding_paths) != len(results) or not all(path.is_file() for path in binding_paths):
        raise ValueError("CALDERA occurrence binding is missing")
    native_occurrences = c0045_native_occurrences() if report.campaign_id == "0.shadowray" else None
    targets = tuple(
        step.contract for step in report.steps
        if step.contract.scope.locus == "target" and (
            step.status == "observed" if native_occurrences is None
            else step.contract.occurrence in native_occurrences
        )
    )
    bound = []
    for path, result in zip(binding_paths, results, strict=True):
        binding = CalderaOccurrenceBinding.model_validate_json(path.read_bytes())
        if binding.command_sha256 != result.dispatch.command_sha256:
            raise ValueError("Occurrence binding differs from the dispatched command")
        if binding.contract not in targets:
            raise ValueError("Dispatched occurrence differs from the observed contract")
        bound.append(binding.contract)
    if len(bound) != len(targets) or any(bound.count(contract) != 1 for contract in targets):
        raise ValueError("CALDERA commands do not cover observed occurrences exactly once")


def verify_journal(evidence: Path) -> CalderaJournalVerification | CalderaJournalVerificationV2:
    session = CalderaSession.model_validate_json((evidence / "caldera-session.json").read_bytes())
    report = _read_campaign_report(evidence)
    results = _verify_dispatches(evidence, session)
    observed = tuple(step for step in report.steps if step.status == "observed")
    target = tuple(step for step in observed if step.contract.scope.locus == "target")
    controller = tuple(step for step in observed if step.contract.scope.locus == "controller")
    counts = dict(
        commands=len(results), observed=len(observed), simulated=report.simulated,
        observed_target=len(target), observed_controller=len(controller),
    )
    if report.campaign_id == "0.shadowray":
        native_occurrences = c0045_native_occurrences()
        simulated_commands = sum(
            step.status == "simulated" and step.contract.occurrence in native_occurrences
            for step in report.steps
        )
        verification = CalderaJournalVerificationV2(
            **counts, simulated_target_commands=simulated_commands,
        )
    else:
        verification = CalderaJournalVerification(**counts)
    verify_occurrence_bindings(evidence, report, results)
    _verify_target_observations(target, session)
    return verification
