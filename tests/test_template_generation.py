from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import ActionTemplate  # noqa: E402
from concretization.provider import (  # noqa: E402
    BudgetConfig,
    ProviderConfig,
    ProviderKind,
)
from concretization.template_generation import (  # noqa: E402
    TemplateGenerationTarget,
    context_bindings_from_generation_batch,
    generate_template_candidates,
)
from concretization.template_proposer import (  # noqa: E402
    TemplateProposalContext,
    trusted_behavior_contract,
)


def _base_template() -> ActionTemplate:
    return ActionTemplate(
        template_id="base-fixture",
        technique_ids=["T1001"],
        execution_domain="target",
        parameter_kinds={"target": "target_host"},
        requires=["sut.ready"],
        produces=["goal.ready"],
        evidence_predicates=["fixture.observed"],
        fidelity_ceiling="adapted",
        description="Exercise a bounded fixture.",
    )


def _config(replay_path: Path, *, max_requests: int = 2) -> ProviderConfig:
    return ProviderConfig(
        provider=ProviderKind.replay,
        model="replay-fixture",
        api_key_env="UNUSED_REPLAY_KEY",
        replay_path=str(replay_path),
        budget=BudgetConfig(max_requests=max_requests),
    )


def _response(path: Path, *, technique_id: str = "T1001") -> None:
    path.write_text(
        json.dumps(
            {
                "template_id": "generated-fixture",
                "technique_ids": [technique_id],
                "execution_domain": "target",
                "parameter_kinds": {"target": "target_host"},
                "requires": ["sut.ready"],
                "produces": ["goal.ready"],
                "evidence_predicates": ["fixture.observed"],
                "fidelity_ceiling": "adapted",
                "description": "Exercise another bounded fixture.",
            }
        ),
        encoding="utf-8",
    )


def _context() -> TemplateProposalContext:
    context = TemplateProposalContext(
        campaign_id="CTEST",
        source_step_index=0,
        source_plan_sha256="a" * 64,
        binding_catalog_sha256="b" * 64,
        execution_domain="target",
        admissible_required_facts=["sut.ready"],
        admissible_produced_facts=["goal.ready"],
        available_binding_kinds=["target_host"],
        existing_template_ids=["base-fixture"],
        admissible_behavior_contracts=[trusted_behavior_contract(_base_template())],
    )
    context.finalize_hash()
    return context


def test_replay_generation_records_budget_calls_and_candidate(tmp_path: Path) -> None:
    replay_path = tmp_path / "response.json"
    _response(replay_path)

    result = generate_template_candidates(
        [
            TemplateGenerationTarget(
                technique_id="T1001",
                technique_summary="Fixture technique",
            )
        ],
        [_base_template()],
        _config(replay_path),
        output_dir=tmp_path / "generation",
        max_attempts_per_target=1,
    )

    assert result.target_count == 1
    assert result.request_count == 1
    assert result.admitted_count == 1
    assert result.templates[0].template_id == "generated-fixture"
    assert result.rows[0].calls[0].provider == "replay"
    assert (tmp_path / "generation/target-000/attempt-01/call_record.json").is_file()


def test_wrong_technique_is_retained_as_bounded_rejection(tmp_path: Path) -> None:
    replay_path = tmp_path / "response.json"
    _response(replay_path, technique_id="T9999")

    result = generate_template_candidates(
        [
            TemplateGenerationTarget(
                technique_id="T1001",
                technique_summary="Fixture technique",
            )
        ],
        [_base_template()],
        _config(replay_path),
        output_dir=tmp_path / "generation",
        max_attempts_per_target=1,
    )

    assert result.request_count == 1
    assert result.admitted_count == 0
    assert result.rows[0].outcome.admission is not None
    assert result.rows[0].outcome.admission.issues[0].code == "technique_scope_mismatch"


def test_replay_generation_enforces_campaign_and_sut_context(tmp_path: Path) -> None:
    replay_path = tmp_path / "response.json"
    _response(replay_path)

    result = generate_template_candidates(
        [
            TemplateGenerationTarget(
                target_id="CTEST:0:T1001:v1",
                technique_id="T1001",
                technique_summary="Fixture technique",
                context=_context(),
            )
        ],
        [_base_template()],
        _config(replay_path),
        output_dir=tmp_path / "contextual-generation",
        max_attempts_per_target=1,
    )

    assert result.admitted_count == 1
    assert result.rows[0].target.context is not None
    assert result.rows[0].target.context.validate_hash()
    bindings = context_bindings_from_generation_batch(result)
    assert bindings[0].candidate_template_id == "generated-fixture"
    assert bindings[0].context.content_sha256 == result.rows[0].target.context.content_sha256


def test_uncontextualized_candidate_cannot_enter_the_promotion_path(tmp_path: Path) -> None:
    replay_path = tmp_path / "response.json"
    _response(replay_path)
    result = generate_template_candidates(
        [
            TemplateGenerationTarget(
                technique_id="T1001",
                technique_summary="Fixture technique",
            )
        ],
        [_base_template()],
        _config(replay_path),
        output_dir=tmp_path / "generation",
        max_attempts_per_target=1,
    )

    with pytest.raises(ValueError, match="lacks a hash-pinned proposal context"):
        context_bindings_from_generation_batch(result)
