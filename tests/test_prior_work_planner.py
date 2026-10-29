from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest  # noqa: E402

from evaluation.controlled_comparison import ArmId, NeutralProposalRecord  # noqa: E402
from concretization.models import ActionTemplate, BindingCatalog, BindingValue  # noqa: E402
from evaluation.prior_work_planner import (  # noqa: E402
    PriorWorkStepContext,
    build_prior_work_prompt,
    propose_prior_work_step,
)

_BUDGET_SHA = "b" * 64


def _context(seed: int = 1) -> PriorWorkStepContext:
    return PriorWorkStepContext(
        experiment_id="EXP1",
        campaign_id="C0026",
        step_id="s3",
        seed=seed,
        technique_id="T1560.001",
        execution_domain="target",
        objective="Archive collected data before exfiltration",
        tactic="collection",
        declared_facts=["actor.ready", "sut.ready"],
        proposal_budget_sha256=_BUDGET_SHA,
    )


def _templates() -> list[ActionTemplate]:
    return [
        ActionTemplate.model_validate(
            {
                "template_id": "archive-local-data",
                "technique_ids": ["T1560.001"],
                "execution_domain": "target",
                "parameter_kinds": {"actor": "actor_host"},
                "requires": ["actor.ready"],
                "produces": ["collection.archive"],
                "evidence_predicates": ["archive_hash_recorded"],
                "fidelity_ceiling": "adapted",
                "description": "Archive declared decoy data locally.",
            }
        )
    ]


def _catalog() -> BindingCatalog:
    catalog = BindingCatalog(
        sut_id="sut1",
        source_sha256="0" * 64,
        bindings=[
            BindingValue(
                binding_id="actor.primary", kind="actor_host", value="lab-actor", source="fixture"
            )
        ],
    )
    catalog.finalize_hash()
    return catalog


def _reply(template_id: str) -> str:
    return json.dumps({"template_id": template_id, "bindings": {"actor": "actor.primary"}})


def test_proposal_is_a_valid_neutral_record():
    record = propose_prior_work_step(_context(), templates=_templates(), catalog=_catalog(),
        complete=lambda system, user: _reply("archive-local-data"))
    assert isinstance(record, NeutralProposalRecord)
    assert record.arm_id == ArmId.prior_work_style
    assert record.template_id == "archive-local-data"
    assert record.campaign_id == "C0026"
    assert record.validate_hash()


def test_malformed_reply_raises_rather_than_repairs():
    with pytest.raises(ValueError):
        propose_prior_work_step(_context(), templates=_templates(), catalog=_catalog(),
            complete=lambda system, user: "I cannot help with that.")


def test_divergent_generations_across_seeds_produce_distinct_records():
    first = propose_prior_work_step(_context(seed=1), templates=_templates(), catalog=_catalog(),
        complete=lambda s, u: _reply("archive-local-data"))
    second = propose_prior_work_step(_context(seed=2), templates=_templates(), catalog=_catalog(),
        complete=lambda s, u: _reply("stage-benign-toolkit"))
    assert first.template_id != second.template_id
    assert first.content_sha256 != second.content_sha256


def test_no_deterministic_admission_is_applied():
    # A template the deterministic verifier would reject is still returned verbatim: this arm does
    # not admit, by design. Admissibility is judged later by the arm-blind oracle.
    record = propose_prior_work_step(_context(), templates=_templates(), catalog=_catalog(),
        complete=lambda s, u: _reply("some-unadmitted-template"))
    assert record.template_id == "some-unadmitted-template"


def test_prompt_exposes_the_matched_inputs():
    prompt = build_prior_work_prompt(_context(), _templates(), _catalog())
    assert "catalog" in prompt
    assert "declared_facts" in prompt
    assert "archive-local-data" in prompt
    assert "parameter_kinds" in prompt
