from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import pytest  # noqa: E402

from collect_controlled_comparison import align_plan_steps, load_campaign_fixture  # noqa: E402


@pytest.mark.parametrize("campaign_id", ["C0010", "C0026", "C0045"])
def test_loader_builds_a_sequential_fact_state(campaign_id):
    fixture = load_campaign_fixture(campaign_id)
    assert fixture.campaign_id == campaign_id
    assert fixture.steps
    # The first step sees the declared initial facts; later steps accumulate produced facts.
    assert set(fixture.steps[0].known_facts) == set(fixture.catalog.initial_facts)
    assert len(fixture.steps[-1].known_facts) >= len(fixture.steps[0].known_facts)
    for step in fixture.steps:
        assert step.technique_id
        assert step.execution_domain


def test_reordered_c0026_keeps_each_techniques_procedural_context():
    procedural_plan = json.loads(
        (PROJECT_ROOT / "release/plans/C0026.procedural-plan.json").read_text()
    )
    procedural_by_technique = {
        step["technique_id"]: step for step in procedural_plan["steps"]
    }
    fixture = load_campaign_fixture("C0026")
    for step in fixture.steps:
        procedure = procedural_by_technique[step.technique_id]
        assert step.execution_domain == procedure["execution_domain"]
        assert step.objective == procedure["name"]
        assert step.tactic == procedure["tactics"][0]


def test_alignment_rejects_missing_procedural_step():
    procedural = [{"technique_id": "T1112"}]
    concretized = [
        {"sequence": 1, "technique_id": "T1112"},
        {"sequence": 2, "technique_id": "T1105"},
    ]
    with pytest.raises(ValueError, match="different step counts"):
        align_plan_steps(procedural, concretized)


def test_alignment_rejects_technique_mismatch():
    procedural = [{"technique_id": "T1112"}]
    concretized = [{"sequence": 1, "technique_id": "T1105"}]
    with pytest.raises(ValueError, match="technique mismatch"):
        align_plan_steps(procedural, concretized)


def test_alignment_rejects_noncontiguous_sequence():
    procedural = [{"technique_id": "T1112"}]
    concretized = [{"sequence": 2, "technique_id": "T1112"}]
    with pytest.raises(ValueError, match="sequence mismatch"):
        align_plan_steps(procedural, concretized)


def test_alignment_follows_concretized_order_without_swapping_context():
    procedural = [
        {"technique_id": "T1005", "execution_domain": "victim"},
        {"technique_id": "T1105", "execution_domain": "attacker"},
    ]
    concretized = [
        {"sequence": 1, "technique_id": "T1105"},
        {"sequence": 2, "technique_id": "T1005"},
    ]
    pairs = align_plan_steps(procedural, concretized)
    assert [procedural_step["technique_id"] for procedural_step, _ in pairs] == [
        "T1105", "T1005"
    ]
    assert [procedural_step["execution_domain"] for procedural_step, _ in pairs] == [
        "attacker", "victim"
    ]


def test_alignment_rejects_ambiguous_repeated_techniques():
    procedural = [{"technique_id": "T1112"}, {"technique_id": "T1112"}]
    concretized = [
        {"sequence": 1, "technique_id": "T1112"},
        {"sequence": 2, "technique_id": "T1112"},
    ]
    with pytest.raises(ValueError, match="explicit step identity"):
        align_plan_steps(procedural, concretized)
