"""Freeze the prospective C0045 compute arm without changing the source campaign."""

import hashlib
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from loaders.campaign_loader import load_campaign
from runners.capability_facts import Digest, ImmutableRecord


ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
STUDY_PATH = ARTIFACT_ROOT / "data/experiments/c0045_compute_effect_v1.json"
CAMPAIGN_PATH = ARTIFACT_ROOT / "campaigns/0.shadowray.json"
SUT_PROFILE_PATH = ARTIFACT_ROOT / "data/sut_profiles/0.shadowray.yml"
PROBE_PATH = ARTIFACT_ROOT / "scripts/probe_target_process_cpu.py"


class C0045ComputeStudy(ImmutableRecord):
    """Versioned design boundary; this record is not an execution result."""

    schema_version: Literal["c0045-compute-effect-study/v1"]
    campaign_id: Literal["0.shadowray"]
    campaign_sha256: Digest
    sut_profile_sha256: Digest
    probe_sha256: Digest
    workload_code_sha256: Digest
    treatment_occurrence: Literal[10]
    technique_id: Literal["T1496.001"]
    source_mode: Literal["naive_simulated"]
    prospective_mode: Literal["real_controlled"]
    target_host_id: Literal["target-linux-1"]
    target_principal: Literal["rayuser"]
    minimum_cpu_ticks: int = Field(strict=True, gt=0)
    sampling_interval_seconds: float = Field(strict=True, gt=0)
    workload_duration_seconds: int = Field(strict=True, gt=0, le=30)
    controls: tuple[Literal["busy", "idle", "controller_only"], ...]
    claim_ceiling: Literal["bounded_guest_compute_only"]

    @model_validator(mode="after")
    def validate_controls(self) -> Self:
        if self.controls != ("busy", "idle", "controller_only"):
            raise ValueError("C0045 controls must remain complete and ordered")
        return self


def _require_source_digest(path: Path, expected: Digest) -> None:
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"C0045 study source changed: {path.name}")


def load_c0045_compute_study() -> C0045ComputeStudy:
    """Reject unreviewed source or campaign-mode drift before treatment."""
    study = C0045ComputeStudy.model_validate_json(STUDY_PATH.read_bytes())
    _require_source_digest(CAMPAIGN_PATH, study.campaign_sha256)
    _require_source_digest(SUT_PROFILE_PATH, study.sut_profile_sha256)
    _require_source_digest(PROBE_PATH, study.probe_sha256)
    campaign = load_campaign(study.campaign_id)
    selected = tuple(
        step for step in campaign.steps if step.order == study.treatment_occurrence
    )
    if (
        len(selected) != 1
        or selected[0].technique_id != study.technique_id
        or selected[0].expected_mode.value != study.source_mode
    ):
        raise ValueError("C0045 source occurrence differs from the study boundary")
    return study
