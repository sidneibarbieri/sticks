import signal
from pathlib import Path

import pytest

from scripts import run_c0045_effect_series_cell as series_cell


def test_fresh_cell_requires_all_managed_vms_to_be_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(series_cell, "vm_state", lambda _vm_name: "running")
    with pytest.raises(RuntimeError, match="requires an absent lab"):
        series_cell.require_absent_lab()


def test_fresh_cell_bootstraps_and_tears_down_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    outcome = object()
    monkeypatch.setattr(series_cell, "require_absent_lab", lambda: None)
    monkeypatch.setattr(series_cell, "run_command", lambda command: calls.append(command))
    monkeypatch.setattr(
        series_cell, "run_c0045_series_cell",
        lambda _cell_id, output_dir, _series_path: (outcome, output_dir / "b1-treatment"),
    )
    observed, root = series_cell.run_fresh_cell("b1-treatment", tmp_path, "qemu")
    assert observed is outcome
    assert root == tmp_path / "b1-treatment"
    assert calls[0][-4:] == ["--campaign", "0.shadowray", "--provider", "qemu"]
    assert calls[1][-2:] == ["--campaign", "0.shadowray"]


def test_fresh_cell_tears_down_after_measurement_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(series_cell, "require_absent_lab", lambda: None)
    monkeypatch.setattr(series_cell, "run_command", lambda command: calls.append(command))
    monkeypatch.setattr(
        series_cell, "run_c0045_series_cell",
        lambda _cell_id, _output_dir, _series_path: (
            _ for _ in ()
        ).throw(RuntimeError("measure")),
    )
    with pytest.raises(RuntimeError, match="measure"):
        series_cell.run_fresh_cell("b1-treatment", tmp_path, "qemu")
    assert calls[-1][-2:] == ["--campaign", "0.shadowray"]


def test_fresh_cell_rejects_out_of_order_selection_before_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(series_cell, "require_absent_lab", lambda: None)
    monkeypatch.setattr(
        series_cell,
        "require_next_c0045_series_cell",
        lambda _cell_id, _output_dir, _series_path: (_ for _ in ()).throw(
            ValueError("Prior C0045 series cell is incomplete: b2-busy")
        ),
    )
    monkeypatch.setattr(series_cell, "run_command", lambda command: calls.append(command))

    with pytest.raises(ValueError, match="b2-busy"):
        series_cell.run_fresh_cell("b2-treatment", tmp_path, "qemu")

    assert calls == []


def test_fresh_cell_retains_post_boot_failure_in_frozen_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fail_bootstrap(command: list[str]) -> None:
        calls.append(command)
        if "up_lab.sh" in command[1]:
            raise RuntimeError("caldera unavailable")

    monkeypatch.setattr(series_cell, "require_absent_lab", lambda: None)
    monkeypatch.setattr(series_cell, "run_command", fail_bootstrap)
    with pytest.raises(RuntimeError, match="caldera unavailable"):
        series_cell.run_fresh_cell("b1-treatment", tmp_path, "qemu")

    outcome_path = tmp_path / "c0045-series-v1/b1-treatment/outcome.json"
    outcome = series_cell.C0045SeriesOutcome.model_validate_json(outcome_path.read_bytes())
    assert outcome.status == "runner_error"
    assert outcome.bootstrap_diagnostic is None
    assert outcome.error_message == "caldera unavailable"
    assert calls[-1][-2:] == ["--campaign", "0.shadowray"]


def test_interruption_handler_raises_keyboard_interrupt() -> None:
    with pytest.raises(KeyboardInterrupt, match="signal"):
        series_cell._raise_interruption(signal.SIGTERM, object())


def test_cleanup_on_termination_restores_previous_handlers() -> None:
    original = signal.getsignal(signal.SIGTERM)
    with series_cell.cleanup_on_termination():
        assert signal.getsignal(signal.SIGTERM) is series_cell._raise_interruption
    assert signal.getsignal(signal.SIGTERM) is original


def test_catchable_termination_tears_down_fresh_lab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(series_cell, "require_absent_lab", lambda: None)
    monkeypatch.setattr(series_cell, "run_command", lambda command: calls.append(command))
    monkeypatch.setattr(
        series_cell,
        "run_c0045_series_cell",
        lambda _cell_id, _output_dir, _series_path: series_cell._raise_interruption(
            signal.SIGTERM, object()
        ),
    )
    with series_cell.cleanup_on_termination(), pytest.raises(KeyboardInterrupt):
        series_cell.run_fresh_cell("b1-treatment", tmp_path, "qemu")
    assert calls[-1][-2:] == ["--campaign", "0.shadowray"]


def test_fresh_cell_recovers_unclosed_attempt_before_starting_new_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    previous_attempt = "previous-attempt"
    series_cell.retain_lifecycle_event(
        tmp_path,
        attempt_id=previous_attempt,
        cell_id="b1-treatment",
        event="boot_started",
    )
    monkeypatch.setattr(series_cell, "require_absent_lab", lambda: None)
    monkeypatch.setattr(
        series_cell,
        "require_next_c0045_series_cell",
        lambda _cell_id, _output_dir, _series_path: None,
    )
    monkeypatch.setattr(series_cell, "run_command", lambda command: calls.append(command))
    monkeypatch.setattr(
        series_cell,
        "run_c0045_series_cell",
        lambda _cell_id, output_dir, _series_path: (object(), output_dir / "b1-busy"),
    )

    series_cell.run_fresh_cell("b1-busy", tmp_path, "qemu")

    assert calls[0][-2:] == ["--campaign", "0.shadowray"]
    events = series_cell.lifecycle_events(tmp_path)
    assert any(
        event.attempt_id == previous_attempt
        and event.event == "recovered_after_interruption"
        for event in events
    )
