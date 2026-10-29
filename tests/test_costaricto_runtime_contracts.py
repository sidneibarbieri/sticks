"""CostaRicto's selected runtime rows must not upgrade legacy declarations."""

import json

import pytest

from executors.campaign_bootstrap import bootstrap_campaign_executors
from executors.executor_registry import registry
from executors.registry_initializer import initialize_registry
from runners.capability_facts import FactScope
from runners.costaricto_runtime_contracts import load_costaricto_runtime_contracts


def guest_scope() -> FactScope:
    return FactScope(
        run_id="run-a",
        environment_id="lab-a",
        epoch="boot-a",
        locus="target",
        host_id="target-linux-1",
        principal="reconuser",
    )


def selected_contracts():
    initialize_registry()
    bootstrap_campaign_executors("0.costaricto")
    return load_costaricto_runtime_contracts(guest_scope(), registry)


def test_exact_ten_occurrences_and_bounded_guest_observers():
    contracts = selected_contracts()
    assert len(contracts) == 10
    assert [contract.occurrence for contract in contracts] == list(range(1, 11))
    assert [
        contract.occurrence
        for contract in contracts
        if contract.mode == "real_controlled"
    ] == [1, 2, 9]
    assert contracts[0].observers == ("costaricto-discovery",)
    assert contracts[1].observers == ("costaricto-transfer",)
    assert contracts[8].observers == ("costaricto-collection",)
    assert all(
        [requirement.name for requirement in contracts[index].requirements]
        == ["lab:shell"]
        for index in (0, 1, 8)
    )
    assert all(
        contract.scope.locus == "controller" and not contract.observers
        for contract in contracts
        if contract.mode == "naive_simulated"
    )


def test_wrong_guest_principal_is_rejected():
    initialize_registry()
    bootstrap_campaign_executors("0.costaricto")
    wrong = FactScope.model_validate(guest_scope().model_dump() | {"principal": "root"})
    with pytest.raises(ValueError, match="declared Linux guest"):
        load_costaricto_runtime_contracts(wrong, registry)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rows: rows.pop(),
        lambda rows: rows[0].update(observers=[]),
        lambda rows: rows[1].update(requirements=[]),
    ],
)
def test_population_or_authority_drift_is_rejected(monkeypatch, mutation):
    from runners import costaricto_runtime_contracts as contracts_module

    initialize_registry()
    bootstrap_campaign_executors("0.costaricto")
    original = contracts_module._CONTRACT_PATH
    population = json.loads(original.read_text())
    mutation(population["occurrences"])

    class ContractBytes:
        def read_bytes(self):
            return json.dumps(population).encode()

    monkeypatch.setattr(contracts_module, "_CONTRACT_PATH", ContractBytes())
    with pytest.raises(ValueError):
        load_costaricto_runtime_contracts(guest_scope(), registry)


def test_executor_source_drift_is_rejected(monkeypatch):
    initialize_registry()
    bootstrap_campaign_executors("0.costaricto")
    original = registry.get_executor

    def different_executor(campaign_id, sut_profile_id):
        return True, "", "", []

    monkeypatch.setattr(
        registry,
        "get_executor",
        lambda technique, campaign=None: (
            different_executor
            if technique == "T1005"
            else original(technique, campaign)
        ),
    )
    with pytest.raises(ValueError, match="Selected executor identity"):
        load_costaricto_runtime_contracts(guest_scope(), registry)
