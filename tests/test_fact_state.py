from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest  # noqa: E402

from concretization.fact_state import AdmissibilityScope, FactState  # noqa: E402


def _state(scope: AdmissibilityScope) -> FactState:
    return FactState(scope=scope, facts=frozenset({"sut.ready"}))


def test_require_serves_facts_under_the_matching_scope():
    state = _state(AdmissibilityScope.sequential)
    assert state.require(AdmissibilityScope.sequential) == frozenset({"sut.ready"})


@pytest.mark.parametrize(
    "held,expected",
    [
        (AdmissibilityScope.hypothetical, AdmissibilityScope.sequential),
        (AdmissibilityScope.initial, AdmissibilityScope.sequential),
        (AdmissibilityScope.sequential, AdmissibilityScope.hypothetical),
    ],
)
def test_require_refuses_a_mismatched_scope(held, expected):
    # The over-admitting hypothetical scope must never be consumed as a sequential one.
    with pytest.raises(ValueError, match="expected a"):
        _state(held).require(expected)


def test_state_is_immutable():
    state = _state(AdmissibilityScope.initial)
    with pytest.raises(Exception):
        state.scope = AdmissibilityScope.sequential


def test_sequential_state_records_the_step_it_describes():
    state = FactState(
        scope=AdmissibilityScope.sequential,
        facts=frozenset({"sut.ready"}),
        reached_technique_id="T1105",
    )
    assert state.reached_technique_id == "T1105"
    assert state.require(AdmissibilityScope.sequential)
