"""The prospective compute arm must never silently rewrite ShadowRay history."""

import pytest
from pydantic import ValidationError

from runners.c0045_compute_study import (
    C0045ComputeStudy,
    load_c0045_compute_study,
)


def test_study_freezes_a_distinct_treatment_from_the_simulated_source() -> None:
    study = load_c0045_compute_study()

    assert study.source_mode == "naive_simulated"
    assert study.prospective_mode == "real_controlled"
    assert study.treatment_occurrence == 10
    assert study.target_host_id == "target-linux-1"
    assert study.target_principal == "rayuser"
    assert study.minimum_cpu_ticks == 5
    assert study.sampling_interval_seconds == 1.0
    assert study.workload_duration_seconds == 15
    assert study.controls == ("busy", "idle", "controller_only")
    assert study.claim_ceiling == "bounded_guest_compute_only"


def test_study_rejects_missing_control() -> None:
    study = load_c0045_compute_study()
    altered = study.model_dump(mode="python")
    altered["controls"] = ("busy", "idle")

    with pytest.raises(ValidationError, match="controls must remain complete"):
        C0045ComputeStudy.model_validate(altered)


def test_study_rejects_changed_source_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    study = load_c0045_compute_study()
    changed = study.model_copy(update={"probe_sha256": "0" * 64})
    monkeypatch.setattr(
        "runners.c0045_compute_study.STUDY_PATH",
        _FakeStudyPath(changed.model_dump_json()),
    )

    with pytest.raises(ValueError, match="source changed: probe_target_process_cpu.py"):
        load_c0045_compute_study()


class _FakeStudyPath:
    def __init__(self, contents: str) -> None:
        self.contents = contents

    def read_bytes(self) -> bytes:
        return self.contents.encode("utf-8")
