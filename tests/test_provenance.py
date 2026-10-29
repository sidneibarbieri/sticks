from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest  # noqa: E402

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from concretization.pipeline import concretize_plan  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402
from evaluation.provenance import (  # noqa: E402
    BindingProvenance,
    MechanismProvenance,
    analyze_plan,
    classify_binding,
    classify_mechanism,
)

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"


def _template(template_id, technique_ids, evidence, domain="target", fidelity="adapted"):
    return {
        "template_id": template_id,
        "technique_ids": technique_ids,
        "execution_domain": domain,
        "evidence_predicates": evidence,
        "produces": [],
        "fidelity_ceiling": fidelity,
    }


SYNTHETIC_TEMPLATES = [
    _template("t-forced", ["T1"], ["e1"]),
    _template("t-a", ["T2"], ["registry_write"]),
    _template("t-b", ["T2"], ["wmi_subscription"]),  # distinct evidence -> proposer_chosen
]


def test_classify_binding_maps_each_documented_source():
    assert classify_binding("stix") is BindingProvenance.cti_evidenced
    assert classify_binding("sut") is BindingProvenance.environment_determined
    assert classify_binding("executor") is BindingProvenance.runtime_derived
    assert classify_binding("system_choice") is BindingProvenance.system_introduced


def test_classify_binding_fails_closed_on_unknown_source():
    with pytest.raises(ValueError):
        classify_binding("anything_else")


def test_classify_mechanism_forced_when_single_template():
    assert (
        classify_mechanism("T1", "target", SYNTHETIC_TEMPLATES)
        is MechanismProvenance.contract_forced
    )


def test_classify_mechanism_proposer_chosen_when_effects_diverge():
    assert (
        classify_mechanism("T2", "target", SYNTHETIC_TEMPLATES)
        is MechanismProvenance.proposer_chosen
    )


def test_analyze_plan_attributes_every_decision():
    catalog_bindings = [
        {"binding_id": "b.stix", "source": "stix"},
        {"binding_id": "b.sut", "source": "sut"},
        {"binding_id": "b.sys", "source": "system_choice"},
    ]
    concretized_steps = [
        {"sequence": 1, "technique_id": "T1", "template_id": "t-forced",
         "bindings": {"p1": "b.stix", "p2": "b.sys"}},
        {"sequence": 2, "technique_id": "T2", "template_id": "t-a",
         "bindings": {"p1": "b.sut"}},
    ]
    result = analyze_plan("CTEST", concretized_steps, catalog_bindings, SYNTHETIC_TEMPLATES)

    assert result.total_steps == 2
    assert result.total_binding_occurrences == 3
    assert result.mechanism_counts[MechanismProvenance.contract_forced] == 1
    assert result.mechanism_counts[MechanismProvenance.proposer_chosen] == 1
    assert result.binding_occurrence_counts[BindingProvenance.cti_evidenced] == 1
    assert result.binding_occurrence_counts[BindingProvenance.environment_determined] == 1
    assert result.binding_occurrence_counts[BindingProvenance.system_introduced] == 1
    assert result.cti_binding_rate == 1 / 3
    assert result.proposer_chosen_mechanism_rate == 1 / 2
    # three distinct binding_ids, each used once here
    assert result.unique_binding_count == 3
    assert result.unique_binding_counts[BindingProvenance.system_introduced] == 1


def test_real_campaign_c0045_provenance_is_report_free_and_contract_forced():
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

    provenance = analyze_plan(
        "C0045",
        result.model_dump(mode="json")["steps"],
        catalog.model_dump(mode="json")["bindings"],
        json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"],
    )

    # The report supplies no executable binding; the environment and the reconstruction do.
    assert provenance.taxonomy_version == "1"
    assert provenance.cti_binding_rate == 0.0
    assert provenance.binding_occurrence_counts[BindingProvenance.system_introduced] == 6
    assert provenance.total_binding_occurrences == 22
    # Mechanism selection was contract-constrained (no proposer-selected mechanism),
    # not a claim that alternatives would behave identically at execution.
    assert provenance.proposer_chosen_mechanism_rate == 0.0
