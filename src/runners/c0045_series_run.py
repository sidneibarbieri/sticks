"""Bind each frozen C0045 study cell to one retained guest run."""

import hashlib
import shutil
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from runners.c0045_compute_study import STUDY_PATH
from runners.c0045_control_replay import verify_c0045_control
from runners.c0045_control_run import run_c0045_control
from runners.c0045_effect_series import (
    SERIES_PATH, ControlArm, c0045_series_sha256, load_c0045_effect_series,
)
from runners.c0045_treatment_replay import verify_c0045_treatment
from runners.c0045_treatment_run import run_c0045_treatment
from runners.capability_facts import Digest, Identity, ImmutableRecord
from runners.capability_observations import _directory, _read_record, _write_exclusive


class C0045SeriesSelection(ImmutableRecord):
    """Written before starting a VM cell; no observed result belongs here."""

    schema_version: Literal["c0045-series-selection/v1"]
    cell_id: Identity
    arm: ControlArm
    order_index: int = Field(strict=True, ge=0, lt=20)
    source_study_sha256: Digest
    series_sha256: Digest


class C0045BootstrapDiagnostic(ImmutableRecord):
    """Host-side facts retained when a fresh laboratory boot fails."""

    phase: Literal["boot"]
    vm_states: dict[Literal["caldera", "attacker", "target-linux-1"], str]

    @model_validator(mode="after")
    def require_complete_topology(self) -> Self:
        if set(self.vm_states) != {"caldera", "attacker", "target-linux-1"}:
            raise ValueError("Bootstrap diagnostic must retain every managed VM state")
        if any(not state for state in self.vm_states.values()):
            raise ValueError("Bootstrap diagnostic contains an empty VM state")
        return self


class C0045SeriesOutcome(C0045SeriesSelection):
    """A complete cell outcome or a retained inability to complete it."""

    schema_version: Literal["c0045-series-selection/v1"]
    status: Literal["observed", "failed", "measured", "runner_error", "boot_reused"]
    run_id: Identity | None
    run_relative_path: str | None
    boot_id: Identity | None
    summary_sha256: Digest | None
    error_type: str | None = None
    error_message: str | None = None
    bootstrap_diagnostic: C0045BootstrapDiagnostic | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if (
            self.arm == "treatment" and self.status == "measured"
            or self.arm != "treatment" and self.status in {"observed", "failed"}
        ):
            raise ValueError("C0045 series status contradicts its selected arm")
        if self.status in {"observed", "failed", "measured", "boot_reused"} and any(
            value is None for value in (
                self.run_id, self.run_relative_path, self.boot_id, self.summary_sha256,
            )
        ):
            raise ValueError("Completed C0045 series cell lacks its underlying run")
        if self.status == "runner_error" and (
            self.error_type is None or self.error_message is None
        ):
            raise ValueError("C0045 series error must retain its reason")
        if self.status == "runner_error" and any(
            value is not None for value in (
                self.run_id, self.run_relative_path, self.boot_id, self.summary_sha256,
            )
        ):
            raise ValueError("C0045 series error cannot assert an unverified run")
        if self.bootstrap_diagnostic is not None and self.status != "runner_error":
            raise ValueError("Bootstrap diagnostic requires a retained runner error")
        return self


def _series_root(output_dir: Path, series_path: Path = SERIES_PATH) -> Path:
    return output_dir / load_c0045_effect_series(series_path).receipt_root_name


def require_c0045_series_output_isolation(
    output_dir: Path, series_path: Path = SERIES_PATH
) -> None:
    """Reject a result directory that already contains another frozen series."""
    expected_root = load_c0045_effect_series(series_path).receipt_root_name
    if not output_dir.exists():
        return
    foreign_roots = sorted(
        child.name
        for child in output_dir.iterdir()
        if child.is_dir()
        and child.name.startswith("c0045-series-v")
        and child.name != expected_root
    )
    if foreign_roots:
        raise ValueError(
            "C0045 output directory already contains another frozen series: "
            + ", ".join(foreign_roots)
        )


def _cell_root(
    output_dir: Path, cell_id: str, series_path: Path = SERIES_PATH
) -> Path:
    return _series_root(output_dir, series_path) / cell_id


def _bootstrap_failure_root(output_dir: Path, cell_id: str) -> Path:
    """Keep host-only boot failures outside the frozen cell result set."""
    return output_dir / "c0045-bootstrap-failures-v1" / cell_id


def _retain(root: Path, filename: str, record: ImmutableRecord) -> None:
    with _directory(None, str(root)) as directory:
        _write_exclusive(directory, filename, record.model_dump_json().encode("utf-8"))


def _read(root: Path, filename: str) -> bytes:
    with _directory(None, str(root)) as directory:
        return _read_record(directory, filename)


def _selected_cell(
    cell_id: str, series_path: Path = SERIES_PATH
) -> C0045SeriesSelection:
    series = load_c0045_effect_series(series_path)
    return C0045SeriesSelection(
        schema_version="c0045-series-selection/v1",
        cell_id=cell_id, arm=series.arm_for(cell_id),
        order_index=series.selected_cells.index(cell_id),
        source_study_sha256=hashlib.sha256(STUDY_PATH.read_bytes()).hexdigest(),
        series_sha256=c0045_series_sha256(series_path),
    )


def retain_c0045_bootstrap_error(
    cell_id: str,
    output_dir: Path,
    attempt_id: str,
    error: Exception,
    vm_states: dict[Literal["caldera", "attacker", "target-linux-1"], str],
) -> C0045SeriesOutcome:
    """Retain a host bootstrap failure without consuming an experimental cell."""
    selection = _selected_cell(cell_id)
    root = _bootstrap_failure_root(output_dir, cell_id) / attempt_id
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(exist_ok=False)
    _retain(root, "selection.json", selection)
    outcome = C0045SeriesOutcome(
        **selection.model_dump(),
        status="runner_error",
        run_id=None,
        run_relative_path=None,
        boot_id=None,
        summary_sha256=None,
        error_type=type(error).__name__,
        error_message=str(error),
        bootstrap_diagnostic=C0045BootstrapDiagnostic(
            phase="boot", vm_states=vm_states
        ),
    )
    _retain(root, "outcome.json", outcome)
    return outcome


def retain_c0045_series_runner_error(
    cell_id: str,
    output_dir: Path,
    error: Exception,
    series_path: Path = SERIES_PATH,
) -> C0045SeriesOutcome:
    """Freeze a post-boot runner error as the outcome of its selected cell."""
    selection = _selected_cell(cell_id, series_path)
    root = _cell_root(output_dir, cell_id, series_path)
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(exist_ok=False)
    _retain(root, "selection.json", selection)
    outcome = C0045SeriesOutcome(
        **selection.model_dump(),
        status="runner_error",
        run_id=None,
        run_relative_path=None,
        boot_id=None,
        summary_sha256=None,
        error_type=type(error).__name__,
        error_message=str(error),
    )
    _retain(root, "outcome.json", outcome)
    return outcome


def quarantine_unbooted_bootstrap_error(cell_id: str, output_dir: Path) -> None:
    """Move a legacy host-only failure away from the frozen experimental cell."""
    root = _cell_root(output_dir, cell_id)
    outcome_path = root / "outcome.json"
    if not outcome_path.is_file():
        return
    outcome = C0045SeriesOutcome.model_validate_json(_read(root, "outcome.json"))
    diagnostic = outcome.bootstrap_diagnostic
    if (
        outcome.status != "runner_error"
        or diagnostic is None
        or any(state != "not_created" for state in diagnostic.vm_states.values())
    ):
        return
    destination = _bootstrap_failure_root(output_dir, cell_id) / "legacy-unbooted"
    if destination.exists():
        raise FileExistsError(f"Bootstrap failure record already exists for {cell_id}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(root), str(destination))


def verify_c0045_series_cell(
    output_dir: Path, cell_id: str, series_path: Path = SERIES_PATH
) -> C0045SeriesOutcome:
    """Replay the joined cell and its source-frozen selection if it completed."""
    expected = _selected_cell(cell_id, series_path)
    root = _cell_root(output_dir, cell_id, series_path)
    selection = C0045SeriesSelection.model_validate_json(_read(root, "selection.json"))
    outcome = C0045SeriesOutcome.model_validate_json(_read(root, "outcome.json"))
    if selection != expected:
        raise ValueError("C0045 series selection differs from frozen schedule")
    if any(
        getattr(outcome, field) != getattr(selection, field)
        for field in C0045SeriesSelection.model_fields
    ):
        raise ValueError("C0045 series outcome differs from selected cell")
    if outcome.status == "runner_error":
        return outcome
    if outcome.run_relative_path is None or Path(outcome.run_relative_path).is_absolute():
        raise ValueError("C0045 series run path is not relative")
    run_root = output_dir / outcome.run_relative_path
    if run_root.resolve().is_relative_to(output_dir.resolve()) is False:
        raise ValueError("C0045 series run path escapes its output directory")
    summary_bytes = _read(run_root, "summary.json")
    if hashlib.sha256(summary_bytes).hexdigest() != outcome.summary_sha256:
        raise ValueError("C0045 series summary differs from its selected receipt")
    report = (
        verify_c0045_treatment(run_root)
        if outcome.arm == "treatment" else verify_c0045_control(run_root, series_path)
    )
    if (
        report.run_id != outcome.run_id
        or report.bootstrap.scope.epoch != outcome.boot_id
        or (outcome.status != "boot_reused" and report.status != outcome.status)
    ):
        raise ValueError("C0045 series cell differs from its replayed run")
    return outcome


def _prior_boot_ids(
    output_dir: Path, order_index: int, series_path: Path = SERIES_PATH
) -> set[str]:
    series = load_c0045_effect_series(series_path)
    boot_ids = set()
    for prior_cell in series.selected_cells[:order_index]:
        if not (_cell_root(output_dir, prior_cell, series_path) / "outcome.json").is_file():
            raise ValueError(f"Prior C0045 series cell is incomplete: {prior_cell}")
        prior = verify_c0045_series_cell(output_dir, prior_cell, series_path)
        if prior.boot_id is not None:
            if prior.boot_id in boot_ids:
                raise ValueError("C0045 series reused a prior guest boot")
            boot_ids.add(prior.boot_id)
    return boot_ids


def require_next_c0045_series_cell(
    cell_id: str, output_dir: Path, series_path: Path = SERIES_PATH
) -> C0045SeriesSelection:
    """Reject an out-of-order or previously retained cell before lab boot."""
    require_c0045_series_output_isolation(output_dir, series_path)
    quarantine_unbooted_bootstrap_error(cell_id, output_dir)
    selection = _selected_cell(cell_id, series_path)
    root = _cell_root(output_dir, cell_id, series_path)
    if root.exists():
        raise ValueError(f"C0045 series cell is already retained: {cell_id}")
    _prior_boot_ids(output_dir, selection.order_index, series_path)
    return selection


def run_c0045_series_cell(
    cell_id: str, output_dir: Path, series_path: Path = SERIES_PATH
) -> tuple[C0045SeriesOutcome, Path]:
    """Run the next selected cell only; preserve errors and duplicate boots."""
    require_c0045_series_output_isolation(output_dir, series_path)
    selection = _selected_cell(cell_id, series_path)
    prior_boot_ids = _prior_boot_ids(output_dir, selection.order_index, series_path)
    root = _cell_root(output_dir, cell_id, series_path)
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(exist_ok=False)
    _retain(root, "selection.json", selection)
    shared = selection.model_dump()
    try:
        if selection.arm == "treatment":
            report, run_root = run_c0045_treatment(output_dir)
        else:
            report, run_root = run_c0045_control(cell_id, output_dir, series_path)
    except Exception as error:
        _retain(root, "outcome.json", C0045SeriesOutcome(
            **shared, status="runner_error", run_id=None,
            run_relative_path=None, boot_id=None, summary_sha256=None,
            error_type=type(error).__name__, error_message=str(error),
        ))
        raise
    boot_id = report.bootstrap.scope.epoch
    status = "boot_reused" if boot_id in prior_boot_ids else report.status
    outcome = C0045SeriesOutcome(
        **shared, status=status, run_id=report.run_id,
        run_relative_path=str(run_root.relative_to(output_dir)), boot_id=boot_id,
        summary_sha256=hashlib.sha256(_read(run_root, "summary.json")).hexdigest(),
        error_type="DuplicateBoot" if status == "boot_reused" else None,
        error_message="Guest boot reused across selected cells" if status == "boot_reused" else None,
    )
    _retain(root, "outcome.json", outcome)
    if status == "boot_reused":
        raise ValueError("C0045 series reused a prior guest boot")
    return outcome, root
