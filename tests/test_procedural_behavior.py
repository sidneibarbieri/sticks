from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from concretization.pipeline import concretize_plan  # noqa: E402
from contracts.procedural_behavior import (  # noqa: E402
    BehaviorComponent,
    assess_element,
)
from contracts.procedural_ir import ProceduralPlan  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"

# Canonical representatives of the other representations (what each supplies).
TTP_ELEMENT = {"technique_id": "T1059.006"}
ATTACK_FLOW_ELEMENT = {
    "technique_id": "T1059.006",
    "sequence": 3,
    "requires": ["prior_access"],
    "produces": ["code_execution"],
    # no evidence_predicates, no bindings: ordered and conditioned, but not executable/checkable
}


def _first_concretized_step() -> dict:
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / "C0045.procedural-plan.json").read_text(encoding="utf-8")
    )
    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / "C0045.binding-catalog.json").read_text(encoding="utf-8")
    )
    templates = [
        ActionTemplate.model_validate(item)
        for item in json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    ]
    result = concretize_plan(plan, catalog, templates, llm_proposals=[])
    return result.model_dump(mode="json")["steps"][0]


def test_ttp_has_only_technique_identity():
    assessment = assess_element(TTP_ELEMENT)
    assert assessment.is_procedural_behavior is False
    assert assessment.present == [BehaviorComponent.technique_identity]


def test_attack_flow_lacks_grounding_and_verification():
    assessment = assess_element(ATTACK_FLOW_ELEMENT)
    assert assessment.is_procedural_behavior is False
    # The precise gap between Attack Flow and procedural behavior:
    assert set(assessment.missing) == {
        BehaviorComponent.verification,
        BehaviorComponent.execution_grounding,
    }


def test_real_sticks_step_is_procedural_behavior():
    assessment = assess_element(_first_concretized_step())
    assert assessment.is_procedural_behavior is True
    assert assessment.missing == []
