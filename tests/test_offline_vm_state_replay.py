"""Offline receipt replay checks recorded teardown without requiring Vagrant."""

from pathlib import Path

import pytest

from scripts import finalize_isolated_lab_run as finalizer


def test_recorded_teardown_does_not_query_vagrant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        finalizer,
        "required_vms",
        lambda unused_root, unused_campaign: ["attacker", "target"],
    )

    def unexpected_vagrant_call(unused_directory: Path) -> str:
        pytest.fail("Offline receipt replay invoked Vagrant")

    monkeypatch.setattr(finalizer, "read_vm_state", unexpected_vagrant_call)

    states = finalizer.receipt_vm_states(
        tmp_path, "0.c0010", {"target": "not_created", "attacker": "not_created"}
    )

    assert states == {"attacker": "not_created", "target": "not_created"}


@pytest.mark.parametrize(
    "recorded_states",
    (
        {},
        {"attacker": "not_created"},
        {"attacker": "not_created", "target": "running"},
        {"attacker": "not_created", "target": "not_created", "other": "not_created"},
        ["not_created", "not_created"],
    ),
)
def test_rejects_incomplete_or_active_recorded_teardown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded_states
) -> None:
    monkeypatch.setattr(
        finalizer,
        "required_vms",
        lambda unused_root, unused_campaign: ["attacker", "target"],
    )

    with pytest.raises(ValueError, match="Recorded VM states"):
        finalizer.receipt_vm_states(tmp_path, "0.c0010", recorded_states)


def test_live_receipt_still_queries_vagrant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        finalizer,
        "required_vms",
        lambda unused_root, unused_campaign: ["attacker", "target"],
    )
    queried: list[str] = []

    def observed_state(directory: Path) -> str:
        queried.append(directory.name)
        return "not_created"

    monkeypatch.setattr(finalizer, "read_vm_state", observed_state)

    states = finalizer.receipt_vm_states(tmp_path, "0.c0010")

    assert states == {"attacker": "not_created", "target": "not_created"}
    assert queried == ["attacker", "target"]
