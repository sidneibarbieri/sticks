"""Deterministic concretization is reproducible from the frozen contract.

Given a campaign's procedural plan, its declared laboratory environment (binding
catalog), and the action-template catalog, the solver-and-verifier pipeline resolves
every step to a fixed execution-semantic hash -- with no LLM and no network. This is the
auditability lock behind the central claim: the admitted procedure is determined by the
declared contract when no external proposal is supplied, so a reviewer reproduces it
offline with zero API keys. This test makes no cross-provider convergence claim.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from concretization.pipeline import concretize_plan  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
SOLVER_SOURCE = "finite_domain_solver"


class ExpectedConcretization(BaseModel):
    """The frozen deterministic outcome for one campaign."""

    model_config = ConfigDict(extra="forbid")

    resolved_steps: int
    execution_semantic_sha256: str


FROZEN_OUTCOMES: dict[str, ExpectedConcretization] = {
    "C0010": ExpectedConcretization(
        resolved_steps=9,
        execution_semantic_sha256="596c7acf49f9a0487b710a86bf2ce09cf4f75fd2fda3b7f022f996689cef2c2a",
    ),
    "C0026": ExpectedConcretization(
        resolved_steps=6,
        execution_semantic_sha256="ed09e8d5fe3915f19405024d59989c27148c84d1608c2af665511a6e5d53ad56",
    ),
    "C0045": ExpectedConcretization(
        resolved_steps=10,
        execution_semantic_sha256="ffe478afcade8f930ea4ef3499e0798c6f0e34d120671f6473fdad09335b86f2",
    ),
}


def _load_templates(path: Path) -> list[ActionTemplate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [ActionTemplate.model_validate(item) for item in payload["templates"]]


@pytest.mark.parametrize("campaign_id", sorted(FROZEN_OUTCOMES))
def test_deterministic_concretization_matches_frozen_contract(campaign_id: str) -> None:
    expected = FROZEN_OUTCOMES[campaign_id]
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
    )
    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
    )
    templates = _load_templates(TEMPLATES_PATH)

    result = concretize_plan(plan, catalog, templates, llm_proposals=[])

    assert result.unresolved_technique_ids == []
    assert len(result.steps) == expected.resolved_steps
    assert result.execution_semantic_sha256 == expected.execution_semantic_sha256
    # No proposer was consulted: the finite-domain solver alone produced every step.
    assert {step.proposal_source for step in result.steps} == {SOLVER_SOURCE}
    # The plan is bound to the exact declared environment it was concretized against.
    assert result.binding_catalog_sha256 == catalog.content_sha256


@pytest.mark.parametrize("campaign_id", sorted(FROZEN_OUTCOMES))
def test_execution_semantics_are_independent_of_unretrieved_templates(campaign_id: str) -> None:
    """Adding a template the plan never retrieves does not change its execution semantics.

    The hash summarizes what is certified to run, so it must not move when the catalog grows
    with templates outside the plan's reach; provenance of the catalog stays on the separate
    content and action-catalog hashes.
    """
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
    )
    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
    )
    templates = _load_templates(TEMPLATES_PATH)
    unreachable = ActionTemplate(
        template_id="unreachable-probe",
        technique_ids=["T9999"],
        execution_domain="target",
        parameter_kinds={"target": "target_host"},
        requires=["access.target.shell"],
        produces=["diagnostic.unreachable"],
        evidence_predicates=["never_recorded"],
        fidelity_ceiling="adapted",
        description="A template no evaluated plan retrieves, used to probe hash coupling.",
    )

    baseline = concretize_plan(plan, catalog, templates, llm_proposals=[])
    grown = concretize_plan(plan, catalog, templates + [unreachable], llm_proposals=[])

    assert grown.execution_semantic_sha256 == baseline.execution_semantic_sha256
    assert grown.action_catalog_sha256 != baseline.action_catalog_sha256
