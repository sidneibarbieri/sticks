from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest  # noqa: E402

from concretization.models import ActionTemplate, BindingCatalog, BindingValue  # noqa: E402
from evaluation.controlled_comparison import ArmId  # noqa: E402
from evaluation.sticks_arm_planner import (  # noqa: E402
    SticksStepContext,
    build_sticks_prompt,
    propose_sticks_step,
)

_BUDGET_SHA = "b" * 64
_TECHNIQUE = "T1021.006"


def _templates() -> list[ActionTemplate]:
    return [
        ActionTemplate.model_validate(
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
    ]


def _catalog() -> BindingCatalog:
    catalog = BindingCatalog(
        sut_id="sut1",
        source_sha256="0" * 64,
        initial_facts=["actor.ready"],
        goal_facts=["access.target.session"],
        bindings=[
            BindingValue(
                binding_id="actor.primary",
                kind="actor_host",
                value="lab-actor",
                source="fixture",
            )
        ],
    )
    catalog.finalize_hash()
    return catalog


def _context(known_facts: list[str]) -> SticksStepContext:
    return SticksStepContext(
        experiment_id="EXP1",
        campaign_id="C0045",
        step_id="s2",
        seed=1,
        technique_id=_TECHNIQUE,
        execution_domain="target",
        known_facts=known_facts,
        proposal_budget_sha256=_BUDGET_SHA,
    )


def _reply(template_id: str) -> str:
    return json.dumps({"template_id": template_id, "bindings": {}})


def test_without_admission_emits_every_proposal():
    outcome = propose_sticks_step(
        _context(known_facts=[]),  # precondition unmet, but this arm does not admit
        templates=_templates(),
        catalog=_catalog(),
        complete=lambda s, u: _reply("open-session"),
        admit=False,
    )
    assert outcome.arm_id == ArmId.sticks_without_admission
    assert outcome.record is not None
    assert not outcome.abstained
    assert outcome.record.validate_hash()


def test_admitted_arm_emits_when_precondition_holds():
    outcome = propose_sticks_step(
        _context(known_facts=["actor.ready"]),
        templates=_templates(),
        catalog=_catalog(),
        complete=lambda s, u: _reply("open-session"),
        admit=True,
    )
    assert outcome.arm_id == ArmId.sticks_admitted
    assert outcome.admitted
    assert not outcome.abstained
    assert outcome.record is not None


def test_admitted_arm_abstains_when_precondition_missing():
    outcome = propose_sticks_step(
        _context(known_facts=[]),  # requires actor.ready, which is absent
        templates=_templates(),
        catalog=_catalog(),
        complete=lambda s, u: _reply("open-session"),
        admit=True,
    )
    assert not outcome.admitted
    assert outcome.abstained
    assert outcome.record is None
    assert outcome.issue_codes


def test_admitted_arm_abstains_on_unknown_template():
    outcome = propose_sticks_step(
        _context(known_facts=["actor.ready"]),
        templates=_templates(),
        catalog=_catalog(),
        complete=lambda s, u: _reply("no-such-template"),
        admit=True,
    )
    assert outcome.abstained
    assert "UNKNOWN_TEMPLATE" in outcome.issue_codes


def test_malformed_reply_raises():
    with pytest.raises(ValueError):
        propose_sticks_step(
            _context(known_facts=["actor.ready"]),
            templates=_templates(),
            catalog=_catalog(),
            complete=lambda s, u: "no json here",
            admit=False,
        )


def test_prompt_filters_templates_with_unmet_preconditions():
    unavailable = ActionTemplate.model_validate(
        {
            "template_id": "requires-unavailable-fact",
            "technique_ids": [_TECHNIQUE],
            "execution_domain": "target",
            "parameter_kinds": {},
            "requires": ["access.target.shell"],
            "produces": ["access.target.session"],
            "evidence_predicates": ["service_request_logged"],
            "fidelity_ceiling": "adapted",
            "description": "Requires a fact that this step does not have.",
        }
    )

    prompt = build_sticks_prompt(
        _context(["actor.ready"]), _templates() + [unavailable], _catalog()
    )

    assert "open-session" in prompt
    assert "requires-unavailable-fact" not in prompt


def test_prompt_filters_bindings_unusable_by_feasible_templates():
    catalog = _catalog().model_copy(
        update={
            "bindings": _catalog().bindings
            + [
                BindingValue(
                    binding_id="artifact.unusable",
                    kind="artifact",
                    value="lab-artifact",
                    source="fixture",
                )
            ]
        }
    )
    template = _templates()[0].model_copy(
        update={"parameter_kinds": {"actor": "actor_host"}}
    )
    prompt = build_sticks_prompt(_context(["actor.ready"]), [template], catalog)

    assert "actor.primary" in prompt
    assert "artifact.unusable" not in prompt
