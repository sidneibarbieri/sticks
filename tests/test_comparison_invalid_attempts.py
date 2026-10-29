"""Malformed model replies remain visible in prospective comparison metrics."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from analyze_controlled_comparison import arm_summary  # noqa: E402
from evaluation.comparison_runner import StepObservation, compute_arm_metrics  # noqa: E402
from evaluation.controlled_comparison import ArmId  # noqa: E402
from evaluation.prior_work_planner import _parse_choice as parse_prior_choice  # noqa: E402
from evaluation.proposal_errors import MalformedProposalError  # noqa: E402
from evaluation.sticks_arm_planner import _parse_choice as parse_sticks_choice  # noqa: E402


@pytest.mark.parametrize("parse_choice", [parse_prior_choice, parse_sticks_choice])
def test_invalid_choice_schema_is_a_malformed_proposal(parse_choice):
    with pytest.raises(MalformedProposalError):
        parse_choice('{"bindings": []}')


def test_parse_failure_counts_as_invalid_attempt_in_both_aggregators():
    valid = StepObservation(
        campaign_id="C0010",
        arm_id=ArmId.prior_work_style,
        seed=1,
        step_id="s1",
        emitted=True,
        abstained=False,
        oracle_admitted=True,
        template_id="template.valid",
    )
    malformed = StepObservation(
        campaign_id="C0010",
        arm_id=ArmId.prior_work_style,
        seed=2,
        step_id="s1",
        emitted=False,
        abstained=False,
        parse_error="response is not a valid prior-work choice",
    )

    metrics = compute_arm_metrics([valid, malformed], ArmId.prior_work_style)
    assert metrics.emitted == 1
    assert metrics.parse_failures == 1
    assert metrics.oracle_valid == 1
    assert metrics.validity_rate == 0.5

    rows = [observation.model_dump(mode="json") for observation in (valid, malformed)]
    summary = arm_summary(rows, ArmId.prior_work_style.value)
    assert summary["emitted"] == 1
    assert summary["valid"] == 1
    assert summary["validity_rate"] == 0.5
    assert summary["mean_distinct_templates_per_step"] == 1.0
