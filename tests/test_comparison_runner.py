from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import ActionTemplate, BindingCatalog, BindingValue  # noqa: E402
from evaluation.comparison_runner import (  # noqa: E402
    CampaignFixture,
    StepFixture,
    build_admitted_campaign_plan,
    compute_arm_metrics,
    observe_step,
)
from evaluation.controlled_comparison import ArmId  # noqa: E402

_BUDGET_SHA = "b" * 64
_ORACLE_REV = "c" * 64
_TECHNIQUE = "T1021.006"


def _fixture() -> CampaignFixture:
    template = ActionTemplate.model_validate(
        {
            "template_id": "open-session",
            "technique_ids": [_TECHNIQUE],
            "execution_domain": "target",
            "parameter_kinds": {},
            "requires": ["actor.ready"],
            "produces": ["access.target.session"],
            "evidence_predicates": ["service_request_logged"],
            "fidelity_ceiling": "adapted",
            "description": "Open a bounded session against the lab target.",
        }
    )
    catalog = BindingCatalog(
        sut_id="sut1",
        source_sha256="0" * 64,
        initial_facts=["actor.ready"],
        goal_facts=["access.target.session"],
        bindings=[
            BindingValue(
                binding_id="actor.primary", kind="actor_host", value="lab-actor", source="fixture"
            )
        ],
    )
    catalog.finalize_hash()
    step = StepFixture(
        step_id="s1",
        technique_id=_TECHNIQUE,
        execution_domain="target",
        objective="Open a remote session on the target",
        tactic="lateral-movement",
        known_facts=["actor.ready"],
    )
    return CampaignFixture(campaign_id="C0045", steps=[step], templates=[template], catalog=catalog)


def _reply(template_id: str) -> str:
    return json.dumps({"template_id": template_id, "bindings": {}})


def _observe(arm_id: ArmId, complete, seed: int = 1, *, retain_proposal: bool = False):
    fixture = _fixture()
    return observe_step(
        arm_id,
        fixture.steps[0],
        fixture,
        seed,
        experiment_id="EXP1",
        budget_sha=_BUDGET_SHA,
        oracle_revision=_ORACLE_REV,
        complete=complete,
        retain_proposal=retain_proposal,
    )


def test_prior_work_emits_and_oracle_admits_a_valid_choice():
    observation = _observe(ArmId.prior_work_style, lambda s, u: _reply("open-session"))
    assert observation.emitted
    assert observation.oracle_admitted is True
    assert observation.template_id == "open-session"


def test_future_collection_retains_exact_proposal_record():
    observation = _observe(
        ArmId.sticks_admitted,
        lambda s, u: _reply("open-session"),
        retain_proposal=True,
    )
    assert observation.proposal_record is not None
    assert observation.proposal_record.content_sha256 == observation.proposal_sha256
    assert observation.proposal_record.template_id == observation.template_id


def test_complete_admitted_arm_builds_exact_execution_plan():
    observation = _observe(
        ArmId.sticks_admitted,
        lambda s, u: _reply("open-session"),
        retain_proposal=True,
    )
    plan = build_admitted_campaign_plan(
        [observation],
        experiment_id="EXP1",
        campaign_id="C0045",
        seed=1,
        collection_lock_sha256="c" * 64,
        expected_step_ids=["s1"],
    )
    assert plan.validate_hash()
    assert [proposal.content_sha256 for proposal in plan.proposals] == [
        observation.proposal_sha256
    ]


def test_execution_plan_rejects_missing_or_unretained_proposal():
    observation = _observe(
        ArmId.sticks_admitted,
        lambda s, u: _reply("open-session"),
    )
    with pytest.raises(ValueError, match="no executable proposal"):
        build_admitted_campaign_plan(
            [observation],
            experiment_id="EXP1",
            campaign_id="C0045",
            seed=1,
            collection_lock_sha256="c" * 64,
            expected_step_ids=["s1"],
        )
    with pytest.raises(ValueError, match="step accounting mismatch"):
        build_admitted_campaign_plan(
            [],
            experiment_id="EXP1",
            campaign_id="C0045",
            seed=1,
            collection_lock_sha256="c" * 64,
            expected_step_ids=["s1"],
        )


def test_admitted_arm_abstains_when_precondition_absent():
    fixture = _fixture()
    step = fixture.steps[0].model_copy(update={"known_facts": []})
    observation = observe_step(
        ArmId.sticks_admitted,
        step,
        fixture,
        1,
        experiment_id="EXP1",
        budget_sha=_BUDGET_SHA,
        oracle_revision=_ORACLE_REV,
        complete=lambda s, u: _reply("open-session"),
    )
    assert not observation.emitted
    assert observation.abstained


def test_malformed_reply_is_recorded_not_raised():
    observation = _observe(ArmId.prior_work_style, lambda s, u: "no json")
    assert not observation.emitted
    assert observation.parse_error is not None


def test_metrics_capture_divergence_across_seeds():
    # The prior-work arm names different templates across seeds; divergence is the measured signal.
    observations = [
        _observe(ArmId.prior_work_style, lambda s, u: _reply("open-session"), seed=1),
        _observe(ArmId.prior_work_style, lambda s, u: _reply("stage-benign-toolkit"), seed=2),
    ]
    metrics = compute_arm_metrics(observations, ArmId.prior_work_style)
    assert metrics.steps == 2
    assert metrics.mean_distinct_templates_per_step == 2.0


def test_metrics_capture_admitted_convergence():
    observations = [
        _observe(ArmId.sticks_admitted, lambda s, u: _reply("open-session"), seed=1),
        _observe(ArmId.sticks_admitted, lambda s, u: _reply("open-session"), seed=2),
    ]
    metrics = compute_arm_metrics(observations, ArmId.sticks_admitted)
    assert metrics.mean_distinct_templates_per_step == 1.0
    assert metrics.abstention_rate == 0.0


def test_divergence_does_not_merge_same_step_id_across_campaigns():
    # step ids repeat across campaigns; keying on step_id alone would merge unrelated steps and
    # report divergence that never happened.
    first = _observe(ArmId.prior_work_style, lambda s, u: _reply("open-session"), seed=1)
    second = _observe(ArmId.prior_work_style, lambda s, u: _reply("stage-benign-toolkit"), seed=1)
    second = second.model_copy(update={"campaign_id": "C0010"})
    metrics = compute_arm_metrics([first, second], ArmId.prior_work_style)
    assert metrics.mean_distinct_templates_per_step == 1.0
