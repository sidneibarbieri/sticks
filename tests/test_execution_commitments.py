from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest  # noqa: E402

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402
from evaluation.execution_commitments import measure_commitments  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"


def _templates() -> list[ActionTemplate]:
    raw = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    return [ActionTemplate.model_validate(item) for item in raw]


def _commitments(campaign_id: str):
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
    )
    declared = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
    )
    return measure_commitments(campaign_id, plan, declared, _templates())


@pytest.mark.parametrize(
    "campaign_id,steps,bindings",
    [("C0010", 9, 19), ("C0026", 6, 13), ("C0045", 10, 22)],
)
def test_commitments_are_fully_determined(campaign_id, steps, bindings):
    commitments = _commitments(campaign_id)
    assert commitments.steps == steps
    assert commitments.mechanism_commitments == steps
    assert commitments.binding_commitments == bindings
    assert commitments.total_execution_commitments == steps + bindings
    assert commitments.fully_determined is True


def test_total_is_the_sum_of_the_parts():
    commitments = _commitments("C0045")
    assert commitments.total_execution_commitments == (
        commitments.mechanism_commitments + commitments.binding_commitments
    )
    assert commitments.candidates_pruned_by_verifier >= 0
