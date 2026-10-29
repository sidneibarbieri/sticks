"""The C0010 review inventory must bind exactly to selected code and loci."""

import json

import pytest

from executors.campaign_bootstrap import bootstrap_campaign_executors
from executors.executor_registry import registry
from executors.lab_transport import resolve_target_vm_name
from executors.registry_initializer import initialize_registry
from runners import c0010_runtime_contracts
from runners.capability_facts import FactScope


@pytest.fixture
def guest_scope():
    initialize_registry()
    bootstrap_campaign_executors("0.c0010")
    return FactScope(
        run_id="c0010-contract-test",
        environment_id="lab-c0010-contract-test",
        epoch="boot-id-test",
        locus="target",
        host_id="target-linux-1",
        principal="ubuntu",
    )


def test_contracts_bind_nine_selected_occurrences(guest_scope):
    assert resolve_target_vm_name("0.c0010") == guest_scope.host_id
    contracts = c0010_runtime_contracts.load_c0010_runtime_contracts(
        guest_scope, registry
    )
    assert tuple(contract.occurrence for contract in contracts) == tuple(range(1, 10))
    assert [contract.scope.locus for contract in contracts] == [
        "controller" for _ in range(8)
    ] + ["target"]
    assert [contract.mode for contract in contracts].count("naive_simulated") == 4
    assert contracts[3].requirements[0].name == "controller:watering_hole_staged"
    assert contracts[3].requirements[0].scope.locus == "controller"
    assert contracts[8].requirements[0].name == "lab:shell"
    assert contracts[8].requirements[0].scope == guest_scope


@pytest.mark.parametrize(
    ("occurrence", "field", "value", "message"),
    [
        (9, "locus", "controller", "target locus"),
        (2, "locus", "target", "target locus"),
        (2, "executor_sha256", "0" * 64, "source differs"),
        (5, "observers", ["c0010-payload"], "observer authority"),
        (4, "requirements", [], "reviewed prerequisites"),
        (9, "plan_sequence", 4, "plan sequences"),
    ],
)
def test_modified_contract_is_rejected(
    guest_scope, monkeypatch, tmp_path, occurrence, field, value, message
):
    population = json.loads(c0010_runtime_contracts._CONTRACT_PATH.read_text())
    population["occurrences"][occurrence - 1][field] = value
    contract_path = tmp_path / "c0010.json"
    contract_path.write_text(json.dumps(population))
    monkeypatch.setattr(c0010_runtime_contracts, "_CONTRACT_PATH", contract_path)
    with pytest.raises(ValueError, match=message):
        c0010_runtime_contracts.load_c0010_runtime_contracts(guest_scope, registry)
