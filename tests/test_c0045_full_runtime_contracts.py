"""The full C0045 contract must retain source modes and exact observed rows."""

import pytest

from executors.campaign_bootstrap import bootstrap_campaign_executors
from executors.executor_registry import registry
from executors.registry_initializer import initialize_registry
from runners.c0045_full_runtime_contracts import load_c0045_full_runtime_contracts
from runners.capability_facts import FactScope


def scope() -> FactScope:
    return FactScope(
        run_id="run-c0045",
        environment_id="lab-c0045",
        epoch="boot-c0045",
        locus="target",
        host_id="target-linux-1",
        principal="rayuser",
    )


def load():
    initialize_registry()
    bootstrap_campaign_executors("0.shadowray")
    return load_c0045_full_runtime_contracts(scope(), registry)


def test_population_preserves_all_source_rows_and_observer_boundaries():
    contracts = load()
    assert [contract.occurrence for contract in contracts] == list(range(1, 11))
    assert [contract.mode for contract in contracts] == [
        "real_controlled",
        "naive_simulated",
        "naive_simulated",
        "naive_simulated",
        "real_controlled",
        "real_controlled",
        "real_controlled",
        "real_controlled",
        "naive_simulated",
        "naive_simulated",
    ]
    assert [contract.observers for contract in contracts] == [
        ("c0045-api",),
        (),
        (),
        (),
        ("c0045-toolkit",),
        ("c0045-transfer",),
        ("c0045-python",),
        ("c0045-network",),
        (),
        (),
    ]
    assert all(
        tuple(requirement.name for requirement in contract.requirements)
        == ("lab:shell",)
        for contract in contracts
    )


def test_contract_rejects_principal_or_executor_drift(monkeypatch):
    with pytest.raises(ValueError, match="declared Linux target"):
        load_c0045_full_runtime_contracts(
            scope().model_copy(update={"principal": "root"}), registry
        )
    initialize_registry()
    bootstrap_campaign_executors("0.shadowray")
    original = registry.get_executor

    def replacement(campaign_id, sut_profile_id):
        return True, "", "", []

    monkeypatch.setattr(
        registry,
        "get_executor",
        lambda technique, campaign=None: (
            replacement if technique == "T1016" else original(technique, campaign)
        ),
    )
    with pytest.raises(ValueError, match="identity differs"):
        load_c0045_full_runtime_contracts(scope(), registry)
