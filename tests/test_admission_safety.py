from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402
from evaluation.admission_safety import (  # noqa: E402
    ProposalKind,
    evaluate_admission_safety,
)

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"


def _result():
    templates = [
        ActionTemplate.model_validate(item)
        for item in json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    ]
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / "C0045.procedural-plan.json").read_text(encoding="utf-8")
    )
    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / "C0045.binding-catalog.json").read_text(encoding="utf-8")
    )
    return evaluate_admission_safety("C0045", plan, catalog, templates, "T1105")


def test_no_inadmissible_proposal_changes_the_committed_plan():
    result = _result()
    assert result.inadmissible_proposals_rejected is True
    for outcome in result.outcomes:
        assert outcome.execution_semantic_sha256 == (
            result.unproposed_execution_semantic_sha256
        )


def test_every_malformed_proposal_kind_is_exercised():
    kinds = {outcome.kind for outcome in _result().outcomes}
    assert kinds == set(ProposalKind)
