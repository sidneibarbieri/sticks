"""Admission safety: what a proposer can and cannot change.

The model lets any source propose a realization, including an unreliable one, because a
deterministic verifier decides admission. This experiment measures the boundary of that
guarantee by submitting proposals of each kind alongside the solver's own candidates and
comparing the committed plan.

Two outcomes are distinguished, and they are not the same property:

  inadmissible proposals cannot be committed. A proposal that names an unknown template,
  the wrong technique, an unavailable binding, or an unsatisfied precondition is rejected,
  and the committed plan is identical to the plan committed without any proposal at all.

  admissible proposals can be selected. When more than one realization is admissible, a
  proposal may be preferred over the solver's default choice. This is by design: the
  proposer chooses among realizations the verifier has already admitted, and the resulting
  plan is admissible either way.

So the guarantee is safety, not proposer-independence: no proposer can cause an
inadmissible realization to be committed, while a proposer may still select among
admissible ones.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from concretization.models import ActionTemplate, BindingCatalog, ProcedureProposal
from concretization.pipeline import concretize_plan
from contracts.procedural_ir import ProceduralPlan


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposalKind(str, Enum):
    none = "none"
    unknown_template = "unknown_template"
    wrong_technique = "wrong_technique"
    unavailable_binding = "unavailable_binding"


class ProposalOutcome(StrictModel):
    kind: ProposalKind
    execution_semantic_sha256: str
    committed_steps: int
    # True when this proposal produced the same plan as submitting no proposal at all.
    matches_unproposed_plan: bool


class AdmissionSafetyResult(StrictModel):
    campaign_id: str
    unproposed_execution_semantic_sha256: str
    outcomes: list[ProposalOutcome]
    # True when no inadmissible proposal changed the committed plan.
    inadmissible_proposals_rejected: bool


def _malformed_proposals(technique_id: str) -> dict[ProposalKind, ProcedureProposal]:
    return {
        ProposalKind.unknown_template: ProcedureProposal(
            technique_id=technique_id,
            template_id="template-that-does-not-exist",
            bindings={},
            source="llm",
        ),
        ProposalKind.wrong_technique: ProcedureProposal(
            technique_id=technique_id,
            template_id="stage-benign-toolkit",
            bindings={"actor": "actor.primary", "toolkit": "toolkit.benign"},
            source="llm",
        ),
        ProposalKind.unavailable_binding: ProcedureProposal(
            technique_id=technique_id,
            template_id="transfer-benign-payload",
            bindings={"actor": "binding.not.in.catalog", "payload": "binding.not.in.catalog"},
            source="llm",
        ),
    }


def evaluate_admission_safety(
    campaign_id: str,
    plan: ProceduralPlan,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
    technique_id: str,
) -> AdmissionSafetyResult:
    baseline = concretize_plan(plan, catalog, templates, llm_proposals=[])
    baseline_hash = baseline.execution_semantic_sha256

    outcomes = [
        ProposalOutcome(
            kind=ProposalKind.none,
            execution_semantic_sha256=baseline_hash,
            committed_steps=len(baseline.steps),
            matches_unproposed_plan=True,
        )
    ]
    for kind, proposal in _malformed_proposals(technique_id).items():
        result = concretize_plan(plan, catalog, templates, llm_proposals=[proposal])
        outcomes.append(
            ProposalOutcome(
                kind=kind,
                execution_semantic_sha256=result.execution_semantic_sha256,
                committed_steps=len(result.steps),
                matches_unproposed_plan=result.execution_semantic_sha256 == baseline_hash,
            )
        )

    return AdmissionSafetyResult(
        campaign_id=campaign_id,
        unproposed_execution_semantic_sha256=baseline_hash,
        outcomes=outcomes,
        inadmissible_proposals_rejected=all(
            outcome.matches_unproposed_plan for outcome in outcomes
        ),
    )
