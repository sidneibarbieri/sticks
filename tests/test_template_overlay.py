from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import (  # noqa: E402
    ActionTemplate,
    BindingCatalog,
    BindingValue,
)
from concretization.realization_space import enumerate_realization_space  # noqa: E402
from concretization.template_generation import CandidateContextBinding  # noqa: E402
from concretization.template_overlay import (  # noqa: E402
    PromotionStatus,
    TemplateImplementationWitness,
    build_template_overlay,
    load_template_overlay,
)
from concretization.template_proposer import (  # noqa: E402
    TemplateProposalContext,
    trusted_behavior_contract,
)
from contracts.procedural_ir import (  # noqa: E402
    ProceduralPlan,
    ProcedureStep,
    SourceSnapshot,
)


def _template(template_id: str, *, parameter_kind: str = "target_host") -> ActionTemplate:
    return ActionTemplate(
        template_id=template_id,
        technique_ids=["T1001"],
        execution_domain="target",
        parameter_kinds={"target": parameter_kind},
        requires=["sut.ready"],
        produces=["goal.ready"],
        evidence_predicates=["fixture.observed"],
        fidelity_ceiling="adapted",
        description="Exercise a bounded fixture.",
    )


def _witness(root: Path, template_id: str, *, expected_hash: str | None = None):
    implementation = root / "executor.py"
    implementation.write_text("def execute():\n    return 'observed'\n", encoding="utf-8")
    return TemplateImplementationWitness(
        template_id=template_id,
        executor_id="fixture.execute",
        implementation_path="executor.py",
        implementation_sha256=expected_hash
        or hashlib.sha256(implementation.read_bytes()).hexdigest(),
        supported_parameter_kinds=["target_host"],
        evidence_predicates=["fixture.observed"],
    )


def _context_binding(
    candidate: ActionTemplate,
    base: ActionTemplate,
) -> CandidateContextBinding:
    context = TemplateProposalContext(
        campaign_id="CTEST",
        source_step_index=0,
        source_plan_sha256="a" * 64,
        binding_catalog_sha256="b" * 64,
        execution_domain="target",
        admissible_required_facts=sorted(base.requires),
        admissible_produced_facts=sorted(base.produces),
        available_binding_kinds=sorted(set(base.parameter_kinds.values())),
        existing_template_ids=[base.template_id],
        admissible_behavior_contracts=[trusted_behavior_contract(base)],
    )
    context.finalize_hash()
    return CandidateContextBinding(
        candidate_template_id=candidate.template_id,
        target_id="CTEST:0:T1001:v1",
        technique_id="T1001",
        context=context,
    )


def test_binds_only_schema_admitted_template_with_matching_witness(tmp_path: Path) -> None:
    base = [_template("base")]
    candidate = _template("candidate")

    result = build_template_overlay(
        base,
        [candidate],
        [_context_binding(candidate, base[0])],
        [_witness(tmp_path, candidate.template_id)],
        artifact_root=tmp_path,
    )

    assert result.implementation_bound_count == 1
    assert result.implementation_bound_templates == [candidate]
    assert result.decisions[0].promotion_status is PromotionStatus.implementation_bound


def test_schema_admitted_template_without_witness_remains_planning_only(tmp_path: Path) -> None:
    base = _template("base")
    candidate = _template("candidate")
    result = build_template_overlay(
        [base],
        [candidate],
        [_context_binding(candidate, base)],
        [],
        artifact_root=tmp_path,
    )

    assert result.planning_only_count == 1
    assert result.implementation_bound_count == 0
    assert result.implementation_bound_templates == []
    assert result.decisions[0].promotion_issues[0].code == "missing_implementation_witness"


def test_missing_context_binding_prevents_implementation_promotion(tmp_path: Path) -> None:
    base = _template("base")
    candidate = _template("candidate")

    result = build_template_overlay(
        [base],
        [candidate],
        [],
        [_witness(tmp_path, candidate.template_id)],
        artifact_root=tmp_path,
    )

    assert result.rejected_count == 1
    assert any(
        issue.code == "missing_candidate_context_binding"
        for issue in result.decisions[0].promotion_issues
    )


def test_hash_mismatch_prevents_execution_promotion(tmp_path: Path) -> None:
    base = _template("base")
    candidate = _template("candidate")
    result = build_template_overlay(
        [base],
        [candidate],
        [_context_binding(candidate, base)],
        [_witness(tmp_path, candidate.template_id, expected_hash="0" * 64)],
        artifact_root=tmp_path,
    )

    assert result.planning_only_count == 1
    assert result.implementation_bound_templates == []
    assert any(
        issue.code == "implementation_hash_mismatch"
        for issue in result.decisions[0].promotion_issues
    )


def test_unknown_parameter_kind_is_rejected_before_witness_promotion(tmp_path: Path) -> None:
    base = _template("base")
    candidate = _template("candidate", parameter_kind="unimplemented_kind")
    result = build_template_overlay(
        [base],
        [candidate],
        [_context_binding(candidate, base)],
        [_witness(tmp_path, candidate.template_id)],
        artifact_root=tmp_path,
    )

    assert result.rejected_count == 1
    assert result.decisions[0].promotion_status is PromotionStatus.rejected
    assert any(
        issue.code == "unknown_parameter_kind"
        for issue in result.decisions[0].schema_admission.issues
    )


def test_overlay_loader_verifies_hash_and_base_catalog(tmp_path: Path) -> None:
    base = [_template("base")]
    candidate = _template("candidate")
    result = build_template_overlay(
        base,
        [candidate],
        [_context_binding(candidate, base[0])],
        [_witness(tmp_path, candidate.template_id)],
        artifact_root=tmp_path,
    )
    path = tmp_path / "overlay.json"
    path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")

    loaded = load_template_overlay(path, base)

    assert loaded.content_sha256 == result.content_sha256
    assert loaded.implementation_bound_templates == [candidate]


def test_symlink_witness_cannot_escape_artifact_root(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir()
    external = tmp_path / "external.py"
    external.write_text("def execute():\n    return 'outside'\n", encoding="utf-8")
    (artifact_root / "executor.py").symlink_to(external)
    candidate = _template("candidate")
    witness = TemplateImplementationWitness(
        template_id=candidate.template_id,
        executor_id="fixture.execute",
        implementation_path="executor.py",
        implementation_sha256=hashlib.sha256(external.read_bytes()).hexdigest(),
        supported_parameter_kinds=["target_host"],
        evidence_predicates=["fixture.observed"],
    )
    base = _template("base")

    result = build_template_overlay(
        [base],
        [candidate],
        [_context_binding(candidate, base)],
        [witness],
        artifact_root=artifact_root,
    )

    assert result.implementation_bound_count == 0
    assert any(
        issue.code == "implementation_path_outside_artifact"
        for issue in result.decisions[0].promotion_issues
    )


def test_implementation_bound_overlay_adds_a_realized_procedure(tmp_path: Path) -> None:
    base = _template("base")
    candidate = _template("candidate")
    overlay = build_template_overlay(
        [base],
        [candidate],
        [_context_binding(candidate, base)],
        [_witness(tmp_path, candidate.template_id)],
        artifact_root=tmp_path,
    )
    plan = ProceduralPlan(
        campaign_id="CTEST",
        campaign_name="Fixture",
        source=SourceSnapshot(
            bundle_sha256="bundle",
            object_count=1,
            campaign_stix_id="campaign--fixture",
            campaign_external_id="CTEST",
        ),
        steps=[
            ProcedureStep(
                technique_id="T1001",
                technique_stix_id="attack-pattern--fixture",
                name="Fixture",
                execution_domain="target",
                relationship_ids=["relationship--fixture"],
            )
        ],
    )
    plan.finalize_hash()
    catalog = BindingCatalog(
        sut_id="sut-fixture",
        source_sha256="source",
        initial_facts=["sut.ready"],
        goal_facts=["goal.ready"],
        bindings=[
            BindingValue(
                binding_id="target.primary",
                kind="target_host",
                value="lab://target-1",
                source="sut",
            )
        ],
    )
    catalog.finalize_hash()

    space = enumerate_realization_space(
        plan,
        catalog,
        [base, *overlay.implementation_bound_templates],
        template_overlay_sha256=overlay.content_sha256,
    )

    assert space.procedure_assignment_variant_count == 2
    assert space.behavior_contract_variant_count == 1
    assert space.step_realization_coverage[0].realized_procedure_assignment_count == 2
    assert space.step_realization_coverage[0].realized_behavior_contract_count == 1
    assert space.template_overlay_sha256 == overlay.content_sha256
