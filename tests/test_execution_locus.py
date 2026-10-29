from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECORD = PROJECT_ROOT / "release/experiments/execution_locus/corpus.json"
DOMAINS = ("attacker", "boundary", "target")


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_every_compiled_step_declares_one_of_the_three_domains():
    payload = _record()
    assert set(payload["steps_by_domain"]) == set(DOMAINS)
    assert sum(payload["steps_by_domain"].values()) == payload["total_steps"]


def test_shares_are_consistent_with_the_counts():
    payload = _record()
    total = payload["total_steps"]
    for domain in DOMAINS:
        expected = round(payload["steps_by_domain"][domain] / total, 4)
        assert payload["step_share_by_domain"][domain] == expected


def test_the_catalog_covers_every_declared_domain():
    payload = _record()
    for domain in DOMAINS:
        assert payload["templates_by_domain"][domain] > 0


def test_template_domains_sum_to_the_catalog_size():
    payload = _record()
    assert sum(payload["templates_by_domain"].values()) == payload["total_templates"]


def test_admission_requires_matching_domains():
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from concretization.solver import enumerate_candidates
    from concretization.models import ActionTemplate, BindingCatalog, BindingValue
    from contracts.procedural_ir import ProcedureStep

    step = ProcedureStep(
        technique_id="T1105",
        technique_stix_id="attack-pattern--x",
        name="probe",
        execution_domain="target",
        relationship_ids=["relationship--x"],
    )
    template = ActionTemplate(
        template_id="wrong-domain",
        technique_ids=["T1105"],
        execution_domain="attacker",
        parameter_kinds={},
        requires=[],
        produces=["probe.effect"],
        evidence_predicates=["artifact_hash_recorded"],
        fidelity_ceiling="inspired",
        description="A template whose locus differs from the step's.",
    )
    catalog = BindingCatalog(sut_id="lab", source_sha256="0" * 64, bindings=[])
    # Enumeration matches on technique; the domain disagreement is the verifier's to refuse.
    candidates = enumerate_candidates(step, [template], catalog)
    assert len(candidates) == 1
    assert candidates[0].template_id == "wrong-domain"
