from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_c0045_effect_series as batch


def test_run_pending_cells_verifies_then_runs_only_absent_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule = SimpleNamespace(selected_cells=("b1-treatment", "b1-busy"))
    complete = SimpleNamespace(cell_id="b1-treatment", status="observed")
    measured = SimpleNamespace(cell_id="b1-busy", status="measured")
    calls: list[str] = []
    monkeypatch.setattr(batch, "load_c0045_effect_series", lambda _path: schedule)
    monkeypatch.setattr(
        batch,
        "retained_outcome",
        lambda _output_dir, cell_id, _series_path: (
            complete if cell_id == "b1-treatment" else None
        ),
    )

    def run_fresh(
        cell_id: str, _output_dir: Path, _provider: str, *args, **kwargs
    ):
        calls.append(cell_id)
        return measured, tmp_path

    monkeypatch.setattr(
        batch,
        "run_fresh_cell",
        run_fresh,
    )

    assert batch.run_pending_cells(tmp_path, "qemu") == [complete, measured]
    assert calls == ["b1-busy"]


def test_retained_outcome_rejects_non_complete_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "c0045-series-v1" / "b1-treatment").mkdir(parents=True)
    failed = SimpleNamespace(status="runner_error")
    monkeypatch.setattr(batch, "verify_c0045_series_cell", lambda *_args: failed)

    with pytest.raises(ValueError, match="not a completed result"):
        batch.retained_outcome(tmp_path, "b1-treatment")
