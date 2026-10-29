from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest  # noqa: E402

from concretization.admissibility import (  # noqa: E402
    admitted_template_ids,
    hypothetical_facts,
    sequential_facts,
)
from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from concretization.pipeline import concretize_plan  # noqa: E402
from concretization.solver import enumerate_candidates  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
CAMPAIGN_ID = "C0045"
TECHNIQUE_ID = "T1105"


def _fixture():
    templates = [
        ActionTemplate.model_validate(item)
        for item in json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    ]
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{CAMPAIGN_ID}.procedural-plan.json").read_text(encoding="utf-8")
    )
    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{CAMPAIGN_ID}.binding-catalog.json").read_text(encoding="utf-8")
    )
    step = next(item for item in plan.steps if item.technique_id == TECHNIQUE_ID)
    committed = concretize_plan(plan, catalog, templates, llm_proposals=[]).steps
    return templates, catalog, step, committed


def test_hypothetical_scope_over_admits_relative_to_sequential():
    templates, catalog, step, committed = _fixture()
    hypothetical = admitted_template_ids(
        step, templates, catalog, hypothetical_facts(catalog, templates)
    )
    sequential = admitted_template_ids(
        step, templates, catalog, sequential_facts(catalog, committed, TECHNIQUE_ID)
    )
    # The hypothetical scope is an upper bound: it can only admit more, never fewer.
    assert set(sequential).issubset(set(hypothetical))
    assert len(hypothetical) >= len(sequential)


def test_sequential_scope_admits_the_template_the_pipeline_commits():
    templates, catalog, step, committed = _fixture()
    sequential = admitted_template_ids(
        step, templates, catalog, sequential_facts(catalog, committed, TECHNIQUE_ID)
    )
    committed_template = next(
        item.template_id for item in committed if item.technique_id == TECHNIQUE_ID
    )
    # What the pipeline commits must be admissible at the state where it commits it.
    assert committed_template in sequential


def test_sequential_facts_are_exactly_the_preceding_steps_effects():
    _, catalog, _, committed = _fixture()
    facts = sequential_facts(catalog, committed, TECHNIQUE_ID)

    expected = set(catalog.initial_facts)
    for item in committed:
        if item.technique_id == TECHNIQUE_ID:
            break
        expected.update(item.produces)
    assert facts == expected


def test_sequential_facts_omit_effects_produced_only_after_the_step():
    _, catalog, _, committed = _fixture()
    facts = sequential_facts(catalog, committed, TECHNIQUE_ID)

    index = next(
        position
        for position, item in enumerate(committed)
        if item.technique_id == TECHNIQUE_ID
    )
    earlier = set(catalog.initial_facts)
    for item in committed[:index]:
        earlier.update(item.produces)
    for item in committed[index:]:
        # A fact only a later step produces must not be assumed to hold at this step.
        for produced in set(item.produces) - earlier:
            assert produced not in facts


def test_enumeration_fails_loud_instead_of_silently_truncating():
    """A truncated candidate set must never be reported as a complete enumeration."""
    templates, catalog, step, _ = _fixture()
    with pytest.raises(ValueError, match="exceeded"):
        enumerate_candidates(step, templates, catalog, maximum_candidates=1)
