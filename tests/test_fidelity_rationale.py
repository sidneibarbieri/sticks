from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_fidelity_rationale import classify, latex_table  # noqa: E402

TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"


def _rows() -> list[dict]:
    templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    return [classify(template) for template in templates]


def test_fidelity_tiers_match_declared_effect_vocabulary():
    # Catalog metadata consistency does not prove execution or predicate correctness.
    for row in _rows():
        if row["fidelity_ceiling"] == "adapted":
            assert row["performs_observable_effect"], row["template_id"]
        else:
            assert not row["performs_observable_effect"], row["template_id"]


def test_inspired_templates_state_what_did_not_happen():
    # Three of the four inspired templates stand in for behavior that would need external systems
    # or real malware; each records the corresponding non-occurrence. assess-privilege-boundary
    # only inspects a declared boundary, so it has no external effect to disclaim.
    inspired = [row for row in _rows() if row["fidelity_ceiling"] == "inspired"]
    assert len(inspired) == 4
    disclaiming = [row for row in inspired if row["non_occurrence_guarantees"]]
    assert len(disclaiming) == 3


def test_latex_table_has_a_bounded_text_column():
    rendered = latex_table(_rows())

    assert r"\begin{tabularx}{\textwidth}" in rendered
    assert r"\end{tabularx}" in rendered


def test_fidelity_table_preserves_every_declared_evidence_predicate():
    templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    for template in templates:
        rendered = latex_table([classify(template)])
        for predicate in template["evidence_predicates"]:
            assert predicate.replace("_", "-") in rendered, template["template_id"]


def test_fidelity_table_labels_obligations_not_execution_results():
    assert "Declared evidence predicates" in latex_table(_rows())
