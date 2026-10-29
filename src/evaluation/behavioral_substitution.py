"""Behavioral substitution: do admissible template alternatives behave the same when run?

Gate-1 finds the steps where more than one template is admissible. Whether those
alternatives are behaviorally equivalent or observably distinct is an execution-level
question: it cannot be settled from declared signatures alone. This module executes each
admissible alternative through an injected executor, records what is observed, and
classifies the step.

Observation is honest about the substrate. Effect, produced facts, evidence-predicate
satisfaction, and host artifacts are compared when observed. Telemetry and detection are
marked ``not_instrumented`` unless the substrate captures them; equality on the observed
dimensions alone is therefore reported as ``inconclusive``, not as full equivalence. When
the execution substrate is unavailable, the step is ``inconclusive`` -- never assumed.

The executor is injected (a callable), so the classifier is testable without a lab and the
same code runs the real lab executor in reproduction.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Substrate(str, Enum):
    lab = "lab"
    local = "local"
    unavailable = "unavailable"


class DimensionResult(str, Enum):
    observed = "observed"
    not_instrumented = "not_instrumented"


class Classification(str, Enum):
    behaviorally_equivalent = "behaviorally_equivalent"
    observably_distinct = "observably_distinct"
    inconclusive = "inconclusive"


class TemplateObservation(StrictModel):
    template_id: str
    substrate: Substrate
    executed: bool
    exit_code: int | None
    evidence_predicate_satisfied: bool | None
    produced_effects: list[str]
    host_artifacts: list[str]
    telemetry: DimensionResult
    detection: DimensionResult


class StepSubstitution(StrictModel):
    campaign_id: str
    technique_id: str
    execution_domain: str
    classification: Classification
    rationale: str
    observations: list[TemplateObservation]


def _observed_signature(observation: TemplateObservation) -> tuple:
    """The dimensions actually observed on the substrate, for equality comparison."""
    return (
        observation.exit_code,
        observation.evidence_predicate_satisfied,
        tuple(sorted(observation.produced_effects)),
        tuple(sorted(observation.host_artifacts)),
    )


def classify_observations(
    observations: list[TemplateObservation],
) -> tuple[Classification, str]:
    executed = [obs for obs in observations if obs.executed]
    if len(executed) < 2:
        return (
            Classification.inconclusive,
            "fewer than two alternatives executed on an available substrate",
        )

    signatures = {_observed_signature(obs) for obs in executed}
    if len(signatures) > 1:
        return (
            Classification.observably_distinct,
            "observed effect, evidence, exit code, or artifacts differ across alternatives",
        )

    fully_instrumented = all(
        obs.telemetry is DimensionResult.observed
        and obs.detection is DimensionResult.observed
        for obs in executed
    )
    if fully_instrumented:
        return (
            Classification.behaviorally_equivalent,
            "all observed dimensions equal, including telemetry and detection",
        )
    return (
        Classification.inconclusive,
        "equal on observed effect, evidence, and artifacts; "
        "telemetry and detection not instrumented",
    )


def unavailable_observation(template_id: str) -> TemplateObservation:
    """Record a template as not executed because the substrate is unavailable."""
    return TemplateObservation(
        template_id=template_id,
        substrate=Substrate.unavailable,
        executed=False,
        exit_code=None,
        evidence_predicate_satisfied=None,
        produced_effects=[],
        host_artifacts=[],
        telemetry=DimensionResult.not_instrumented,
        detection=DimensionResult.not_instrumented,
    )


def evaluate_step(
    campaign_id: str,
    technique_id: str,
    execution_domain: str,
    admissible_template_ids: list[str],
    observe: Callable[[str], TemplateObservation],
) -> StepSubstitution:
    """Observe each admissible template via ``observe`` and classify the step.

    ``observe`` returns a TemplateObservation for a template_id; in reproduction it runs the
    lab executor, and it returns an unavailable observation when the substrate is absent.
    """
    observations = [observe(template_id) for template_id in sorted(admissible_template_ids)]
    classification, rationale = classify_observations(observations)
    return StepSubstitution(
        campaign_id=campaign_id,
        technique_id=technique_id,
        execution_domain=execution_domain,
        classification=classification,
        rationale=rationale,
        observations=observations,
    )
