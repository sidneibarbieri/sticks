from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import ActionTemplate  # noqa: E402
from evaluation.authoring_cost import (  # noqa: E402
    AutomationYield,
    measure_authoring_cost,
    template_surface,
)

YIELD = AutomationYield(proposals=10, admitted=8, rejected=2, rejected_by_code={"unknown_predicate": 2})


def _template(template_id: str, technique: str, parameters: int, effects: int) -> ActionTemplate:
    return ActionTemplate(
        template_id=template_id,
        technique_ids=[technique],
        execution_domain="target",
        parameter_kinds={f"p{index}": "target_host" for index in range(parameters)},
        requires=["host.ready"],
        produces=[f"state.{index}" for index in range(effects)],
        evidence_predicates=["file_exists"],
        fidelity_ceiling="adapted",
        description="test template",
    )


def test_the_surface_counts_every_declared_field() -> None:
    surface = template_surface(_template("a", "T1005", parameters=2, effects=3))
    assert (surface.parameters, surface.requirements, surface.effects, surface.evidence_predicates) == (2, 1, 3, 1)
    assert surface.fields == 7


def test_reuse_counts_only_corpus_steps_of_covered_techniques() -> None:
    templates = [_template("a", "T1005", 1, 1), _template("b", "T1083", 1, 1)]
    cost = measure_authoring_cost(templates, {"T1005": 6, "T1083": 2, "T9999": 50}, YIELD)
    assert cost.covered_steps == 8
    assert cost.steps_per_template == 4.0
    assert cost.covered_techniques == 2


def test_the_automation_yield_is_carried_unchanged() -> None:
    cost = measure_authoring_cost([_template("a", "T1005", 1, 1)], {"T1005": 1}, YIELD)
    assert cost.automation == YIELD


def test_an_empty_catalog_is_refused() -> None:
    with pytest.raises(ValueError, match="no templates"):
        measure_authoring_cost([], {}, YIELD)
