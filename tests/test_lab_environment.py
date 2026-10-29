"""A declared environment can be derived from the catalog rather than authored per campaign.

Authoring one binding catalog per campaign is what limited execution to three campaigns.
The templates already declare the parameter kinds they consume and the facts they require,
so the environment a plan needs follows from the catalog.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.lab_environment import (  # noqa: E402
    DERIVED_SOURCE,
    derive_lab_environment,
    reachable_templates,
    unproducible_facts,
)
from concretization.models import ActionTemplate  # noqa: E402
from concretization.pipeline import concretize_plan  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
CORPUS_RECORD = PROJECT_ROOT / "release" / "experiments" / "derived_environment" / "corpus.json"


def _templates() -> list[ActionTemplate]:
    raw = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    return [ActionTemplate.model_validate(item) for item in raw]


def _plan(campaign_id: str) -> ProceduralPlan:
    return ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
    )


def test_derived_environment_admits_the_campaign_steps():
    templates = _templates()
    plan = _plan("C0045")
    environment = derive_lab_environment("lab.derived.c0045", templates, plan)
    result = concretize_plan(plan, environment, templates, llm_proposals=[])
    assert len(result.steps) == len(plan.steps)


def test_every_derived_binding_is_recorded_as_a_system_choice():
    environment = derive_lab_environment("lab.derived", _templates(), _plan("C0045"))
    # Provenance must keep reporting these values as introduced, never as CTI evidence.
    assert {binding.source for binding in environment.bindings} == {DERIVED_SOURCE}
    assert {binding.scope.value for binding in environment.bindings} == {"lab"}


def test_initial_facts_are_exactly_what_execution_cannot_produce():
    templates = _templates()
    plan = _plan("C0045")
    scoped = reachable_templates(plan, templates)
    environment = derive_lab_environment("lab.derived", templates, plan)
    assert set(environment.initial_facts) == unproducible_facts(scoped)


def test_derivation_is_deterministic():
    templates, plan = _templates(), _plan("C0026")
    first = derive_lab_environment("lab.derived", templates, plan)
    second = derive_lab_environment("lab.derived", templates, plan)
    assert first.content_sha256 == second.content_sha256


def test_corpus_record_matches_a_recomputed_campaign():
    """The frozen corpus numbers come from this derivation, not from a separate path."""
    record = json.loads(CORPUS_RECORD.read_text(encoding="utf-8"))
    assert record["campaigns"] == len(record["per_campaign"])
    assert record["admitted_steps"] == sum(
        row["admitted_steps"] for row in record["per_campaign"]
    )
    sample = record["per_campaign"][0]
    templates = _templates()
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / "enterprise" / f"{sample['campaign_id']}.procedural-plan.json").read_text(
            encoding="utf-8"
        )
    )
    environment = derive_lab_environment(
        f"lab.derived.{sample['campaign_id'].lower()}", templates, plan
    )
    result = concretize_plan(plan, environment, templates, llm_proposals=[])
    assert len(result.steps) == sample["admitted_steps"]
