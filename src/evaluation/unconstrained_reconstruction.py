"""Measure how much independent proposers diverge when nothing constrains them.

This is the counterfactual to finite-domain admission: the same CTI steps and declared
environment, but no catalog and no verifier. Each proposer commits a free-choice realization,
and the question is whether independent proposers commit the same executable procedure.

Divergence is measured at the decision level, not over surface text, and reported as a
spectrum so no single normalization decides the result:

  method              -- did they pick the same mechanism at all?
  executable_decision -- same mechanism, target, and concrete parameters?
  command             -- the literal command string (surface upper bound on divergence)

Agreement on the executable decision is the fair comparison to the finite-domain arm, whose
committed execution converges to one hash under the same models and temperature. Reporting the
method level separately shows whether proposers disagree even on the choice of mechanism.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

_WHITESPACE = re.compile(r"\s+")


class Reconstruction(BaseModel):
    """One proposer's free-choice realization of a single step."""

    model_config = ConfigDict(extra="forbid")

    technique_id: str
    proposer: str
    mechanism: str
    target: str = ""
    command: str = ""
    parameters: dict[str, str] = Field(default_factory=dict)


class StepDivergence(BaseModel):
    """Distinct reconstructions of one step across proposers, at three levels."""

    model_config = ConfigDict(extra="forbid")

    technique_id: str
    reconstruction_count: int
    distinct_methods: int
    distinct_executable_decisions: int
    distinct_commands: int
    decision_agreement_rate: float


class DeterministicControl(BaseModel):
    """Cross-proposer divergence with sampling disabled.

    Sampled divergence could in principle be a generator artifact rather than a property of
    what the report leaves open. Repeating the arm at temperature 0 separates the two: if a
    proposer reproduces its own output yet two proposers still write different procedures,
    the disagreement is not produced by sampling. Reproducibility is recorded per proposer
    because a serving stack may remain non-deterministic even at temperature 0.
    """

    model_config = ConfigDict(extra="forbid")

    proposers_per_step: int
    mean_distinct_procedures: float
    steps_with_full_agreement: int
    pairwise_agreement_rate: float
    within_proposer_reproducible: dict[str, bool] = Field(default_factory=dict)


class CatalogOnlyArm(BaseModel):
    """Divergence when the catalog is supplied but admission is not applied.

    The unconstrained arm removes the catalog and the verifier together, so it cannot say
    which of the two produces agreement. This arm supplies the same catalog through the same
    prompt and records whatever the proposer returns, without the admission predicate.
    Comparing it against the other two separates restricting the space of realizations from
    deciding admission over that space.
    """

    model_config = ConfigDict(extra="forbid")

    steps: int
    proposers_per_step: int
    mean_distinct_realizations: float
    steps_with_full_agreement: int
    pairwise_agreement_rate: float
    proposals_outside_catalog: int
    malformed_proposals: int


class DivergenceCorpus(BaseModel):
    """Corpus-wide unconstrained divergence, paired against finite-domain convergence."""

    model_config = ConfigDict(extra="forbid")

    question: str = (
        "Given the same CTI and declared environment, do independent unconstrained proposers "
        "commit the same executable procedure?"
    )
    method: str = (
        "The same steps and declared environment as the finite-domain arm are given to the same "
        "local models at the same temperature, with no action catalog and no verifier. Each "
        "proposer commits a free-choice realization; divergence is counted at the method, "
        "executable-decision, and command levels."
    )
    campaigns: int
    steps: int
    proposers_per_step: int
    mean_distinct_methods: float
    mean_distinct_executable_decisions: float
    mean_distinct_commands: float
    steps_with_full_method_agreement: int
    steps_with_full_decision_agreement: int
    mean_decision_agreement_rate: float
    deterministic_control: DeterministicControl | None = None
    catalog_only_arm: CatalogOnlyArm | None = None
    per_step: list[StepDivergence] = Field(default_factory=list)
    note: str = ""


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip().lower())


def _method_signature(reconstruction: Reconstruction) -> str:
    return _normalize(reconstruction.mechanism)


def _executable_decision_signature(reconstruction: Reconstruction) -> str:
    parameters = ";".join(
        f"{_normalize(name)}={_normalize(value)}"
        for name, value in sorted(reconstruction.parameters.items())
    )
    return "|".join(
        (
            _normalize(reconstruction.mechanism),
            _normalize(reconstruction.target),
            parameters,
        )
    )


def _pairwise_agreement(signatures: list[str]) -> float:
    """Fraction of proposer pairs that committed the same executable decision."""
    pair_count = len(signatures) * (len(signatures) - 1) // 2
    if pair_count == 0:
        return 1.0
    agreements = sum(
        1
        for first in range(len(signatures))
        for second in range(first + 1, len(signatures))
        if signatures[first] == signatures[second]
    )
    return agreements / pair_count


def step_divergence(reconstructions: list[Reconstruction]) -> StepDivergence:
    """Count distinct reconstructions of one step at each level."""
    if not reconstructions:
        raise ValueError("a step needs at least one reconstruction to measure divergence")
    decisions = [_executable_decision_signature(item) for item in reconstructions]
    return StepDivergence(
        technique_id=reconstructions[0].technique_id,
        reconstruction_count=len(reconstructions),
        distinct_methods=len({_method_signature(item) for item in reconstructions}),
        distinct_executable_decisions=len(set(decisions)),
        distinct_commands=len({_normalize(item.command) for item in reconstructions}),
        decision_agreement_rate=_pairwise_agreement(decisions),
    )


def aggregate(per_step: list[StepDivergence], *, note: str, campaigns: int) -> DivergenceCorpus:
    """Fold per-step divergence into corpus totals."""
    if not per_step:
        raise ValueError("no steps to aggregate")
    step_count = len(per_step)
    proposers = max(step.reconstruction_count for step in per_step)
    return DivergenceCorpus(
        campaigns=campaigns,
        steps=step_count,
        proposers_per_step=proposers,
        mean_distinct_methods=sum(s.distinct_methods for s in per_step) / step_count,
        mean_distinct_executable_decisions=sum(
            s.distinct_executable_decisions for s in per_step
        )
        / step_count,
        mean_distinct_commands=sum(s.distinct_commands for s in per_step) / step_count,
        steps_with_full_method_agreement=sum(1 for s in per_step if s.distinct_methods == 1),
        steps_with_full_decision_agreement=sum(
            1 for s in per_step if s.distinct_executable_decisions == 1
        ),
        mean_decision_agreement_rate=sum(s.decision_agreement_rate for s in per_step)
        / step_count,
        per_step=per_step,
        note=note,
    )
