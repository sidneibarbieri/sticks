from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest  # noqa: E402

from concretization.models import ActionTemplate  # noqa: E402
from concretization.template_admission import (  # noqa: E402
    admit_template,
    build_admission_vocabulary,
    fact_namespace,
)

TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"


def _catalog() -> list[ActionTemplate]:
    payload = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    return [ActionTemplate.model_validate(item) for item in payload["templates"]]


@pytest.fixture(scope="module")
def vocabulary():
    return build_admission_vocabulary(_catalog())


def test_every_curated_template_is_admitted(vocabulary):
    # The verifier must accept the trusted ground truth; rejecting a hand-curated template
    # would mean the admission rules are stricter than the framework itself.
    for template in _catalog():
        admission = admit_template(template, vocabulary)
        assert admission.admitted, (template.template_id, admission.issues)


def _reference_template() -> ActionTemplate:
    return ActionTemplate.model_validate(
        {
            "template_id": "candidate-under-test",
            "technique_ids": ["T1071.001"],
            "execution_domain": "attacker",
            "parameter_kinds": {"actor": "actor_host"},
            "requires": ["actor.ready"],
            "produces": ["c2:channel_open"],
            "evidence_predicates": ["http_request_logged"],
            "fidelity_ceiling": "adapted",
            "description": "Reference candidate expressed in the implemented vocabulary.",
        }
    )


def test_reference_candidate_is_admitted(vocabulary):
    assert admit_template(_reference_template(), vocabulary).admitted


def test_ungrounded_evidence_predicate_is_rejected(vocabulary):
    candidate = _reference_template().model_copy(
        update={"evidence_predicates": ["screenshot_uploaded_to_cloud"]}
    )
    admission = admit_template(candidate, vocabulary)
    assert not admission.admitted
    assert any(issue.code == "ungrounded_evidence_predicate" for issue in admission.issues)


def test_fidelity_ceiling_above_honest_bound_is_rejected(vocabulary):
    candidate = _reference_template().model_copy(update={"fidelity_ceiling": "real"})
    admission = admit_template(candidate, vocabulary)
    assert not admission.admitted
    assert any(issue.code == "unbounded_fidelity_ceiling" for issue in admission.issues)


def test_unmodelled_namespace_is_rejected(vocabulary):
    candidate = _reference_template().model_copy(update={"produces": ["quantum:entangled"]})
    admission = admit_template(candidate, vocabulary)
    assert not admission.admitted
    assert any(issue.code == "unknown_produced_namespace" for issue in admission.issues)


def test_unimplemented_parameter_kind_is_rejected(vocabulary):
    candidate = _reference_template().model_copy(
        update={"parameter_kinds": {"target": "invented_resource"}}
    )
    admission = admit_template(candidate, vocabulary)
    assert not admission.admitted
    assert any(issue.code == "unknown_parameter_kind" for issue in admission.issues)


def test_no_state_progress_is_rejected(vocabulary):
    candidate = _reference_template().model_copy(update={"produces": ["actor.ready"]})
    admission = admit_template(candidate, vocabulary)
    assert not admission.admitted
    assert any(issue.code == "no_state_progress" for issue in admission.issues)


def test_privilege_without_precondition_is_rejected(vocabulary):
    candidate = _reference_template().model_copy(
        update={"requires": [], "produces": ["credentials:dumped"]}
    )
    admission = admit_template(candidate, vocabulary)
    assert not admission.admitted
    assert any(issue.code == "privilege_without_precondition" for issue in admission.issues)


def test_malformed_technique_id_is_rejected(vocabulary):
    candidate = _reference_template().model_copy(update={"technique_ids": ["not-a-technique"]})
    admission = admit_template(candidate, vocabulary)
    assert not admission.admitted
    assert any(issue.code == "malformed_technique_id" for issue in admission.issues)


def test_fact_namespace_extraction():
    assert fact_namespace("actor.ready") == "actor"
    assert fact_namespace("artifacts:recon_toolkit") == "artifacts"
    assert fact_namespace("c2_channel") == "c2_channel"


def test_fidelity_taxonomy_is_the_declared_three_tiers():
    from concretization.models import FidelityTier

    assert [tier.value for tier in FidelityTier] == ["faithful", "adapted", "inspired"]


def test_catalog_never_claims_faithful_reproduction(vocabulary):
    # A laboratory surrogate is never the documented product, version, and mechanism. The catalog
    # topping out at adapted is the honest ceiling, and the verifier enforces it.
    assert "faithful" not in vocabulary.fidelity_ceilings
    assert vocabulary.fidelity_ceilings == frozenset({"adapted", "inspired"})
