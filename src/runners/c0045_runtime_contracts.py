"""Construct the one-row prospective C0045 contract without changing ShadowRay."""

import hashlib
from pathlib import Path
from typing import Literal

from executors.c0045_compute_executor import execute_c0045_compute_treatment
from executors.executor_registry import ExecutorMetadata, ExecutorRegistry
from executors.models import ExecutionFidelity, ExecutionMode
from runners.c0045_compute_study import STUDY_PATH, load_c0045_compute_study
from runners.capability_facts import CapabilityRequirement, Digest, FactScope, ImmutableRecord
from runners.runtime_step_contracts import RuntimeStepContract, verify_executor_binding


CONTRACT_PATH = Path(__file__).resolve().parents[2] / "data/runtime_contracts/c0045_compute.json"


class C0045RuntimeBinding(ImmutableRecord):
    """Reviewed prospective executor and observer, not the source campaign mode."""

    schema_version: Literal["c0045-compute-runtime/v1"]
    study_sha256: Digest
    executor_id: Literal[
        "executors.c0045_compute_executor.execute_c0045_compute_treatment"
    ]
    executor_sha256: Digest
    observer: Literal["c0045-compute"]
    requirement: Literal["lab:shell"]
    product: Literal["compute:bounded_guest_cpu"]


def c0045_treatment_registry() -> ExecutorRegistry:
    """Keep the prospective binding isolated from the legacy campaign registry."""
    study = load_c0045_compute_study()
    selected = ExecutorRegistry()
    selected.register(
        study.technique_id,
        ExecutorMetadata(
            technique_id=study.technique_id,
            technique_name="Bounded target compute treatment",
            execution_mode=ExecutionMode.REAL_CONTROLLED,
            produces=["compute:bounded_guest_cpu"],
            requires=["lab:shell"],
            safe_simulation=False,
            cleanup_supported=True,
            description="Reviewed non-network guest hash loop for measured CPU effect",
            platform="linux",
            execution_fidelity=ExecutionFidelity.ADAPTED,
            fidelity_justification="Bounded guest CPU use, not Ray exploitation",
            original_platform="linux",
            requires_privilege="user",
        ),
        execute_c0045_compute_treatment,
        campaign_id=study.campaign_id,
    )
    return selected


def load_c0045_runtime_contract(
    guest_scope: FactScope, selected_registry: ExecutorRegistry
) -> RuntimeStepContract:
    """Require the frozen study, source bytes, guest scope, and selected executor."""
    study = load_c0045_compute_study()
    binding = C0045RuntimeBinding.model_validate_json(CONTRACT_PATH.read_bytes())
    if hashlib.sha256(STUDY_PATH.read_bytes()).hexdigest() != binding.study_sha256:
        raise ValueError("C0045 runtime binding differs from the frozen study")
    if (
        guest_scope.locus != "target"
        or guest_scope.host_id != study.target_host_id
        or guest_scope.principal != study.target_principal
    ):
        raise ValueError("C0045 runtime requires the declared guest scope")
    contract = RuntimeStepContract(
        campaign_id=study.campaign_id,
        occurrence=study.treatment_occurrence,
        technique_id=study.technique_id,
        executor_id=binding.executor_id,
        executor_sha256=binding.executor_sha256,
        mode=study.prospective_mode,
        scope=guest_scope,
        requirements=(CapabilityRequirement(
            name=binding.requirement, scope=guest_scope,
            accepted_origins=frozenset({"observed"}),
        ),),
        observers=(binding.observer,),
    )
    executor = selected_registry.get_executor(study.technique_id, study.campaign_id)
    metadata = selected_registry.get_metadata(study.technique_id, study.campaign_id)
    if (
        executor is None
        or metadata is None
        or metadata.execution_mode.value != study.prospective_mode
        or metadata.produces != [binding.product]
    ):
        raise ValueError("C0045 runtime has no matching selected executor")
    verify_executor_binding(contract, executor)
    return contract
