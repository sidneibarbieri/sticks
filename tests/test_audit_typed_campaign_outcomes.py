"""Typed outcome audit must keep controller and guest effects distinct."""

from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import audit_typed_campaign_outcomes as outcome_audit
from scripts.audit_typed_campaign_outcomes import summarize_run


def _step(status: str, locus: str | None = None) -> dict:
    observations = [{"passed": True, "scope": {"locus": locus}}] if locus else []
    return {"status": status, "outcome": {"observations": observations}}


def _records() -> tuple[dict, dict]:
    receipt = {
        "campaign_id": "0.c0010",
        "run_id": "run-one",
        "source_tree_sha256": "a" * 64,
        "cycle_passed": True,
        "controller_effects_observed": 1,
        "guest_effects_observed": 1,
        "simulated": 1,
    }
    summary = {
        "schema_version": "runtime-campaign/v2",
        "campaign_id": "0.c0010",
        "run_id": "run-one",
        "steps": [
            _step("observed", "controller"),
            _step("observed", "target"),
            _step("simulated"),
        ],
        "total_techniques": 3,
        "effects_observed": 2,
        "simulated": 1,
        "failed": 0,
    }
    return receipt, summary


def test_separates_controller_target_and_simulation() -> None:
    receipt, summary = _records()
    outcome = summarize_run(receipt, summary, "b" * 64)
    assert (
        outcome.observed_controller,
        outcome.observed_target,
        outcome.simulated,
    ) == (1, 1, 1)
    assert outcome.total == 3


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda receipt, summary: summary.update(run_id="other"), "different runs"),
        (lambda receipt, summary: summary.update(effects_observed=3), "totals"),
        (
            lambda receipt, summary: receipt.update(guest_effects_observed=2),
            "Receipt disagrees",
        ),
        (
            lambda receipt, summary: summary["steps"][0]["outcome"][
                "observations"
            ].clear(),
            "one passed observation",
        ),
        (
            lambda receipt, summary: summary["steps"][1]["outcome"]["observations"][0][
                "scope"
            ].update(locus="boundary"),
            "unsupported locus",
        ),
        (
            lambda receipt, summary: summary["steps"][2]["outcome"][
                "observations"
            ].append({"passed": True, "scope": {"locus": "target"}}),
            "Non-observed step",
        ),
    ),
)
def test_rejects_inconsistent_outcomes(mutation, message: str) -> None:
    receipt, summary = deepcopy(_records())
    mutation(receipt, summary)
    with pytest.raises(ValueError, match=message):
        summarize_run(receipt, summary, "b" * 64)


def test_comparison_rejects_different_source_trees(monkeypatch, tmp_path) -> None:
    receipt, summary = _records()
    first = summarize_run(receipt, summary, "b" * 64)
    second = first.model_copy(
        update={
            "campaign_id": "0.c0026",
            "run_id": "run-two",
            "source_tree_sha256": "c" * 64,
        }
    )
    outcomes = iter((first, second))
    monkeypatch.setattr(outcome_audit, "audit_run", lambda unused_root: next(outcomes))

    with pytest.raises(ValueError, match="same source tree"):
        outcome_audit.audit_runs([tmp_path / "first", tmp_path / "second"])
