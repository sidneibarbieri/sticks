from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest  # noqa: E402

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402
from evaluation.enrichment_baseline import empty_environment, run_baseline  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"


def _templates() -> list[ActionTemplate]:
    raw = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    return [ActionTemplate.model_validate(item) for item in raw]


def test_empty_environment_strips_bindings_and_facts_and_rehashes():
    declared = BindingCatalog.model_validate_json(
        (PLANS_DIR / "C0045.binding-catalog.json").read_text(encoding="utf-8")
    )
    raw = empty_environment(declared)
    assert raw.bindings == []
    assert raw.initial_facts == []
    assert raw.goal_facts == []
    assert raw.validate_hash()
    assert raw.content_sha256 != declared.content_sha256


@pytest.mark.parametrize(
    "campaign_id,total,enriched",
    [("C0010", 9, 9), ("C0026", 6, 6), ("C0045", 10, 10)],
)
def test_raw_stix_executes_nothing_enriched_executes_all(campaign_id, total, enriched):
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
    )
    declared = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
    )
    result = run_baseline(campaign_id, plan, declared, _templates())

    assert result.total_steps == total
    # Raw STIX supplies the plan but nothing executable.
    assert result.raw_stix_executable_steps == 0
    assert result.raw_stix_executable_rate == 0.0
    # The declared environment makes every step executable.
    assert result.enriched_executable_steps == enriched
    assert result.enrichment_delta == enriched
    assert result.enriched_executable_rate == 1.0
