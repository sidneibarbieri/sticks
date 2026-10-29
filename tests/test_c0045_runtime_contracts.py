"""Prospective C0045 contract is distinct from the simulated ShadowRay row."""

from pathlib import Path

import pytest

from loaders.campaign_loader import load_campaign
from runners.c0045_runtime_contracts import (
    c0045_treatment_registry,
    load_c0045_runtime_contract,
)
from runners.capability_facts import FactScope


def guest_scope() -> FactScope:
    return FactScope(
        run_id="run-c0045", environment_id="lab-c0045", epoch="boot-c0045",
        locus="target", host_id="target-linux-1", principal="rayuser",
    )


def test_prospective_binding_preserves_source_campaign_mode() -> None:
    registry = c0045_treatment_registry()
    contract = load_c0045_runtime_contract(guest_scope(), registry)
    source = load_campaign("0.shadowray")

    assert contract.occurrence == 10
    assert contract.mode == "real_controlled"
    assert contract.observers == ("c0045-compute",)
    assert tuple(requirement.name for requirement in contract.requirements) == (
        "lab:shell",
    )
    assert source.steps[9].expected_mode.value == "naive_simulated"
    assert source.steps[9].produces == ["simulation:bounded_compute_recorded"]


def test_runtime_binding_rejects_wrong_guest_and_executor_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = c0045_treatment_registry()
    with pytest.raises(ValueError, match="declared guest"):
        load_c0045_runtime_contract(
            guest_scope().model_copy(update={"principal": "root"}), registry
        )

    from runners import c0045_runtime_contracts

    changed = tmp_path / "binding.json"
    changed.write_text(
        c0045_runtime_contracts.CONTRACT_PATH.read_text().replace(
            '"executor_sha256": "79c5', '"executor_sha256": "09c5'
        )
    )
    monkeypatch.setattr(c0045_runtime_contracts, "CONTRACT_PATH", changed)
    with pytest.raises(ValueError, match="source differs"):
        load_c0045_runtime_contract(guest_scope(), registry)
