"""Campaign-level objective validation over a completed runtime report.

Per-step predicates certify that one step produced its declared effect. They do
not say whether the campaign achieved the adversary's objective: the motivating
point is that a capability obtained in one step must enable a later one, so an
emulation succeeds only when the terminal capabilities the objective names were
actually established.

A clause is met *by observation* only when the terminal fact traces to the step
that produced it: a step that ran under controlled authority, was independently
observed, granted exactly that fact, and bound the observation bytes to it. A
fact asserted in isolation, a simulated fact, or a fact whose observation is not
bound to an observed producer step does not meet an observed requirement. The
validator reads a retained report; it runs nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from runners.capability_facts import (
    CapabilityFact,
    FactOrigin,
    Identity,
    ImmutableRecord,
)
from runners.capability_observations import verify_observation_reference
from runners.runtime_campaign_report import RuntimeCampaignReport, RuntimeCampaignStep

# Mirrors FactScope.locus; a clause may pin the locus where the capability must hold.
Locus = Literal["controller", "attacker", "target"]
Description = Annotated[str, StringConstraints(strict=True, min_length=1)]


class ObjectiveClause(ImmutableRecord):
    """One terminal capability; omitted scope selectors match any value."""

    fact: Identity
    locus: Locus | None = None
    host_id: Identity | None = None
    principal: Identity | None = None
    require_observed: bool = True


class CampaignObjective(ImmutableRecord):
    """The capabilities a campaign must establish, declared before a run."""

    campaign_id: Identity
    description: Description
    clauses: tuple[ObjectiveClause, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_clauses(self) -> CampaignObjective:
        keys = [
            (clause.fact, clause.locus, clause.host_id, clause.principal)
            for clause in self.clauses
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("Objective clauses must have distinct fact and scope")
        return self


class ClauseVerdict(ImmutableRecord):
    """Whether one clause was met, and whether an observed producer step backs it."""

    clause: ObjectiveClause
    satisfied: bool
    observation_bound: bool
    origin: FactOrigin | None
    producer_occurrence: int | None


class CampaignObjectiveVerdict(ImmutableRecord):
    """Whether the campaign achieved its objective, and whether by observation."""

    campaign_id: Identity
    run_id: Identity
    achieved: bool
    achieved_via_observation: bool
    clauses: tuple[ClauseVerdict, ...]


def _matching_facts(
    facts: tuple[CapabilityFact, ...], clause: ObjectiveClause
) -> list[CapabilityFact]:
    return [
        fact
        for fact in facts
        if fact.name == clause.fact
        and (clause.locus is None or fact.scope.locus == clause.locus)
        and (clause.host_id is None or fact.scope.host_id == clause.host_id)
        and (clause.principal is None or fact.scope.principal == clause.principal)
    ]


def _observed_producer(
    report: RuntimeCampaignReport, fact: CapabilityFact
) -> RuntimeCampaignStep | None:
    """The observed step that granted this fact with its observation bytes bound."""
    if fact.origin != "observed" or fact.producer_occurrence is None:
        return None
    for step in report.steps:
        if (
            step.status == "observed"
            and step.outcome is not None
            and step.contract.occurrence == fact.producer_occurrence
            and fact in step.outcome.authorizing_facts
            and fact.observation is not None
            and fact.observation in step.outcome.observation_references
        ):
            return step
    return None


def _clause_verdict(
    report: RuntimeCampaignReport, clause: ObjectiveClause
) -> ClauseVerdict:
    bound_fact = next(
        (
            fact
            for fact in _matching_facts(report.runtime_facts, clause)
            if _observed_producer(report, fact) is not None
        ),
        None,
    )
    fact = bound_fact or next(iter(_matching_facts(report.runtime_facts, clause)), None)
    observation_bound = bound_fact is not None
    satisfied = fact is not None and (not clause.require_observed or observation_bound)
    return ClauseVerdict(
        clause=clause,
        satisfied=satisfied,
        observation_bound=observation_bound,
        origin=fact.origin if fact is not None else None,
        producer_occurrence=fact.producer_occurrence if fact is not None else None,
    )


def validate_objective(
    report: RuntimeCampaignReport, objective: CampaignObjective
) -> CampaignObjectiveVerdict:
    """Decide whether a completed campaign report meets its declared objective."""
    if report.campaign_id != objective.campaign_id:
        raise ValueError("Objective and report describe different campaigns")
    verdicts = tuple(_clause_verdict(report, clause) for clause in objective.clauses)
    achieved = all(verdict.satisfied for verdict in verdicts)
    achieved_via_observation = achieved and all(
        verdict.observation_bound for verdict in verdicts
    )
    return CampaignObjectiveVerdict(
        campaign_id=report.campaign_id,
        run_id=report.run_id,
        achieved=achieved,
        achieved_via_observation=achieved_via_observation,
        clauses=verdicts,
    )


def verify_objective_receipts(
    report: RuntimeCampaignReport, objective: CampaignObjective, run_root: Path
) -> CampaignObjectiveVerdict:
    """Check retained bytes for observed clauses; this is not an end-state oracle."""
    verdict = validate_objective(report, objective)
    for clause, clause_verdict in zip(objective.clauses, verdict.clauses, strict=True):
        if not clause_verdict.observation_bound:
            continue
        for fact in _matching_facts(report.runtime_facts, clause):
            step = _observed_producer(report, fact)
            if step is None:
                continue
            if fact.scope.run_id != report.run_id:
                raise ValueError("Objective fact belongs to another run")
            reference = fact.observation
            if reference is None or step.outcome is None:
                raise ValueError(
                    "Observed objective fact lacks a producing observation"
                )
            observation = verify_observation_reference(
                reference,
                run_root=run_root,
                expected_scope=fact.scope,
                expected_predicate=reference.predicate_id,
            )
            if (
                observation not in step.outcome.observations
                or not observation.passed
                or fact.name not in observation.established_facts
            ):
                raise ValueError("Retained observation differs from the producer step")
            break
    return verdict


def load_objective(path: Path) -> CampaignObjective:
    """Load a declared campaign objective from its frozen JSON file."""
    return CampaignObjective.model_validate_json(path.read_text(encoding="utf-8"))


def unobservable_facts(
    objective: CampaignObjective, observable: frozenset[str]
) -> tuple[Identity, ...]:
    """Observed-required clauses whose terminal fact no observer can establish.

    A non-empty result means the objective declares a goal the lab cannot prove by
    observation; it would never be achieved-via-observation however the run goes.
    """
    return tuple(
        clause.fact
        for clause in objective.clauses
        if clause.require_observed and clause.fact not in observable
    )
