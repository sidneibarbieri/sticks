"""Freeze C0045 effect/control cells independently of the earlier diagnostic run."""

import hashlib
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from runners.c0045_compute_study import STUDY_PATH, load_c0045_compute_study
from runners.capability_facts import Digest, Identity, ImmutableRecord


SERIES_PATH = (
    Path(__file__).resolve().parents[2]
    / "data/experiments/c0045_compute_effect_series_v1.json"
)
SERIES_V2_PATH = (
    Path(__file__).resolve().parents[2]
    / "data/experiments/c0045_compute_effect_series_v2.json"
)
SERIES_PATHS = frozenset({SERIES_PATH.resolve(), SERIES_V2_PATH.resolve()})
ControlArm = Literal["treatment", "busy", "idle", "controller_only"]
CONTROL_ARMS: tuple[ControlArm, ...] = (
    "treatment", "busy", "idle", "controller_only",
)


class C0045EffectSeries(ImmutableRecord):
    """A fixed 5-by-4 schedule; it contains no observed outcome."""

    schema_version: Literal[
        "c0045-compute-effect-series/v1",
        "c0045-compute-effect-series/v2",
    ]
    source_study_sha256: Digest
    prior_treatment_run: Identity
    prior_treatment_role: Literal["diagnostic_excluded"]
    unit: Literal["fresh_guest_boot_per_cell"]
    selected_cells: tuple[str, ...]
    stopping_rule: Literal["run_all_20_selected_cells_record_failures_and_unsupported"]
    claim_ceiling: Literal["bounded_guest_compute_controlled_calibration_only"]
    predecessor_series_sha256: Digest | None = None
    predecessor_status: Literal["interrupted_post_boot_dependency_failure"] | None = None

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        expected = {
            f"b{block}-{arm}"
            for block in range(1, 6)
            for arm in CONTROL_ARMS
        }
        if len(self.selected_cells) != 20 or set(self.selected_cells) != expected:
            raise ValueError("C0045 series must select every arm in five blocks")
        if self.schema_version.endswith("/v1") and (
            self.predecessor_series_sha256 is not None
            or self.predecessor_status is not None
        ):
            raise ValueError("C0045 v1 cannot declare a predecessor")
        if self.schema_version.endswith("/v2") and (
            self.predecessor_series_sha256 is None
            or self.predecessor_status is None
        ):
            raise ValueError("C0045 v2 must declare its interrupted predecessor")
        return self

    def arm_for(self, cell_id: str) -> ControlArm:
        if cell_id not in self.selected_cells:
            raise ValueError("C0045 cell is not in the frozen schedule")
        return cell_id.split("-", 1)[1]

    @property
    def receipt_root_name(self) -> str:
        """Name the result root after the immutable schedule revision."""
        version = self.schema_version.rsplit("/v", 1)[1]
        return f"c0045-series-v{version}"


def load_c0045_effect_series(
    series_path: Path = SERIES_PATH,
) -> C0045EffectSeries:
    """Reject drift from the source study before running any selected cell."""
    series_path = series_path.resolve()
    if series_path not in SERIES_PATHS:
        raise ValueError("C0045 series path is not a declared frozen schedule")
    load_c0045_compute_study()
    series = C0045EffectSeries.model_validate_json(series_path.read_bytes())
    if hashlib.sha256(STUDY_PATH.read_bytes()).hexdigest() != series.source_study_sha256:
        raise ValueError("C0045 effect series differs from its frozen source study")
    return series


def c0045_series_sha256(series_path: Path = SERIES_PATH) -> Digest:
    """Return the digest only after accepting the declared schedule path."""
    load_c0045_effect_series(series_path)
    return hashlib.sha256(series_path.read_bytes()).hexdigest()
