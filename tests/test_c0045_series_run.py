"""A C0045 series cannot skip cells, reuse boots, or hide failed attempts."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from runners.c0045_series_run import (
    C0045SeriesOutcome, quarantine_unbooted_bootstrap_error,
    require_c0045_series_output_isolation,
    retain_c0045_bootstrap_error, retain_c0045_series_runner_error,
    run_c0045_series_cell,
    verify_c0045_series_cell,
)
from runners.c0045_effect_series import SERIES_V2_PATH


def _fake_run(output_dir: Path, name: str, boot_id: str, status: str):
    root = output_dir / name
    root.mkdir(parents=True, exist_ok=False)
    (root / "summary.json").write_text("{}", encoding="utf-8")
    report = SimpleNamespace(
        run_id=name, status=status,
        bootstrap=SimpleNamespace(scope=SimpleNamespace(epoch=boot_id)),
    )
    return report, root


def test_series_requires_selected_order_and_retains_runner_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="Prior C0045 series cell is incomplete"):
        run_c0045_series_cell("b1-busy", tmp_path)

    def fail_treatment(_output_dir):
        raise RuntimeError("lab not ready")

    monkeypatch.setattr(
        "runners.c0045_series_run.run_c0045_treatment", fail_treatment
    )
    with pytest.raises(RuntimeError, match="lab not ready"):
        run_c0045_series_cell("b1-treatment", tmp_path)
    root = tmp_path / "c0045-series-v1/b1-treatment"
    error = C0045SeriesOutcome.model_validate_json(
        (root / "outcome.json").read_bytes()
    )
    assert error.status == "runner_error" and error.error_type == "RuntimeError"
    assert verify_c0045_series_cell(tmp_path, "b1-treatment") == error
    with pytest.raises(FileExistsError):
        run_c0045_series_cell("b1-treatment", tmp_path)


def test_series_retains_bootstrap_error_with_all_vm_states(tmp_path: Path) -> None:
    outcome = retain_c0045_bootstrap_error(
        "b1-treatment",
        tmp_path,
        "attempt-1",
        RuntimeError("caldera unavailable"),
        {"caldera": "running", "attacker": "running", "target-linux-1": "running"},
    )

    assert outcome.status == "runner_error"
    assert outcome.bootstrap_diagnostic is not None
    diagnostic_root = tmp_path / "c0045-bootstrap-failures-v1/b1-treatment/attempt-1"
    stored = C0045SeriesOutcome.model_validate_json(
        (diagnostic_root / "outcome.json").read_bytes()
    )
    assert stored == outcome


def test_series_rejects_receipts_from_another_frozen_schedule(
    tmp_path: Path,
) -> None:
    (tmp_path / "c0045-series-v1").mkdir()

    with pytest.raises(ValueError, match="another frozen series: c0045-series-v1"):
        require_c0045_series_output_isolation(tmp_path, SERIES_V2_PATH)


def test_series_retains_post_boot_error_in_selected_cell(tmp_path: Path) -> None:
    outcome = retain_c0045_series_runner_error(
        "b1-treatment", tmp_path, RuntimeError("profile dependency missing")
    )

    assert outcome.status == "runner_error"
    assert outcome.bootstrap_diagnostic is None
    assert verify_c0045_series_cell(tmp_path, "b1-treatment") == outcome


def test_series_quarantines_legacy_unbooted_bootstrap_error(tmp_path: Path) -> None:
    root = tmp_path / "c0045-series-v1/b1-treatment"
    root.mkdir(parents=True)
    selection = C0045SeriesOutcome(
        **{
            "schema_version": "c0045-series-selection/v1",
            "cell_id": "b1-treatment",
            "arm": "treatment",
            "order_index": 0,
            "source_study_sha256": "0" * 64,
            "series_sha256": "1" * 64,
            "status": "runner_error",
            "run_id": None,
            "run_relative_path": None,
            "boot_id": None,
            "summary_sha256": None,
            "error_type": "RuntimeError",
            "error_message": "host unavailable",
            "bootstrap_diagnostic": {
                "phase": "boot",
                "vm_states": {
                    "caldera": "not_created",
                    "attacker": "not_created",
                    "target-linux-1": "not_created",
                },
            },
        }
    )
    (root / "outcome.json").write_bytes(selection.model_dump_json().encode())

    quarantine_unbooted_bootstrap_error("b1-treatment", tmp_path)

    assert not root.exists()
    assert (
        tmp_path
        / "c0045-bootstrap-failures-v1/b1-treatment/legacy-unbooted/outcome.json"
    ).is_file()


def test_series_joins_run_and_rejects_reused_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    treatment, treatment_root = _fake_run(tmp_path, "treatment-run", "boot-1", "observed")
    monkeypatch.setattr(
        "runners.c0045_series_run.run_c0045_treatment",
        lambda _output_dir: (treatment, treatment_root),
    )
    monkeypatch.setattr(
        "runners.c0045_series_run.verify_c0045_treatment", lambda _root: treatment
    )
    first, _ = run_c0045_series_cell("b1-treatment", tmp_path)
    assert first.status == "observed"
    assert verify_c0045_series_cell(tmp_path, "b1-treatment") == first

    control, control_root = _fake_run(tmp_path, "control-run", "boot-1", "measured")
    monkeypatch.setattr(
        "runners.c0045_series_run.run_c0045_control",
        lambda _cell_id, _output_dir, _series_path: (control, control_root),
    )
    monkeypatch.setattr(
        "runners.c0045_series_run.verify_c0045_control",
        lambda _root, _series_path: control,
    )
    with pytest.raises(ValueError, match="reused a prior guest boot"):
        run_c0045_series_cell("b1-busy", tmp_path)
    invalid = verify_c0045_series_cell(tmp_path, "b1-busy")
    assert invalid.status == "boot_reused" and invalid.boot_id == "boot-1"
    with pytest.raises(ValueError, match="reused a prior guest boot"):
        run_c0045_series_cell("b1-idle", tmp_path)


def test_series_detects_tampered_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    treatment, treatment_root = _fake_run(tmp_path, "treatment-run", "boot-1", "observed")
    monkeypatch.setattr(
        "runners.c0045_series_run.run_c0045_treatment",
        lambda _output_dir: (treatment, treatment_root),
    )
    monkeypatch.setattr(
        "runners.c0045_series_run.verify_c0045_treatment", lambda _root: treatment
    )
    run_c0045_series_cell("b1-treatment", tmp_path)
    (treatment_root / "summary.json").write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="summary differs"):
        verify_c0045_series_cell(tmp_path, "b1-treatment")


def test_series_rejects_arm_status_mismatch() -> None:
    with pytest.raises(ValueError, match="contradicts its selected arm"):
        C0045SeriesOutcome.model_validate({
            "schema_version": "c0045-series-selection/v1",
            "cell_id": "b1-busy", "arm": "busy", "order_index": 1,
            "source_study_sha256": "a" * 64,
            "series_sha256": "b" * 64,
            "status": "observed", "run_id": "run", "run_relative_path": "run",
            "boot_id": "boot", "summary_sha256": "c" * 64,
        })
