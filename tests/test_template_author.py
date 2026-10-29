from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.evidence_policy import PredicateRole, load_roles
from curation.template_author import (
    AdmissionVocabulary,
    RejectionCode,
    admit_proposal,
)

VOCAB = AdmissionVocabulary(
    predicate_roles={
        "artifact_hash_recorded": PredicateRole.effect,
        "no_external_transfer": PredicateRole.safety,
    },
    bindable_kinds=frozenset({"target_host", "payload"}),
)


def _proposal(**overrides):
    base = {
        "template_id": "probe-template",
        "technique_ids": ["T1082"],
        "execution_domain": "target",
        "parameter_kinds": {"target": "target_host"},
        "requires": [],
        "produces": ["probe.effect"],
        "evidence_predicates": ["artifact_hash_recorded"],
        "fidelity_ceiling": "adapted",
        "description": "A synthetic probe template.",
    }
    base.update(overrides)
    return base


def test_a_well_formed_proposal_is_admitted():
    outcome = admit_proposal("T1082", _proposal(), VOCAB)
    assert outcome.admitted
    assert outcome.template is not None


def test_a_proposal_for_a_different_technique_is_rejected():
    outcome = admit_proposal("T1057", _proposal(), VOCAB)
    assert outcome.rejection_code is RejectionCode.technique_drift


def test_an_invented_predicate_is_rejected():
    outcome = admit_proposal("T1082", _proposal(evidence_predicates=["made_up_signal"]), VOCAB)
    assert outcome.rejection_code is RejectionCode.unknown_predicate


def test_a_safety_only_policy_is_rejected():
    outcome = admit_proposal("T1082", _proposal(evidence_predicates=["no_external_transfer"]), VOCAB)
    assert outcome.rejection_code is RejectionCode.no_effect_predicate


def test_a_faithful_claim_is_rejected():
    outcome = admit_proposal("T1082", _proposal(fidelity_ceiling="faithful"), VOCAB)
    assert outcome.rejection_code is RejectionCode.overclaimed_fidelity


def test_an_unbindable_parameter_kind_is_rejected():
    outcome = admit_proposal("T1082", _proposal(parameter_kinds={"x": "quantum_host"}), VOCAB)
    assert outcome.rejection_code is RejectionCode.unbindable_parameter


def test_a_malformed_proposal_is_rejected_not_raised():
    outcome = admit_proposal("T1082", {"template_id": "x"}, VOCAB)
    assert outcome.rejection_code is RejectionCode.malformed_schema


def test_the_gate_is_deterministic_over_a_proposal():
    first = admit_proposal("T1082", _proposal(), VOCAB)
    second = admit_proposal("T1082", _proposal(), VOCAB)
    assert first.admitted == second.admitted


def test_the_frozen_run_reproduces_its_recorded_counts():
    record = json.loads(
        (PROJECT_ROOT / "release/experiments/stage2_authoring/corpus.json").read_text(
            encoding="utf-8"
        )
    )
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "stage2_report", PROJECT_ROOT / "scripts/build_stage2_authoring_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert record == module.build_report()
    assert record["extended_contract_reach_steps"] <= record["total_steps"]
    assert record["admitted_templates"] + sum(record["rejected_by_code"].values()) == record["proposals"]


def test_every_admitted_draft_is_well_formed_and_review_pending():
    draft_root = PROJECT_ROOT / "data/concretization/proposed_templates"
    drafts = list(draft_root.glob("*.json"))
    assert drafts, "No preserved draft templates found"
    for path in drafts:
        draft = json.loads(path.read_text(encoding="utf-8"))
        assert draft["lifecycle"] == "draft"
        assert draft["provenance"]["review_pending"] is True
        assert draft["template"]["fidelity_ceiling"] in ("adapted", "inspired")
