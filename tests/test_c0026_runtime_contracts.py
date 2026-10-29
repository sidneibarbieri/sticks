"""Fixed C0026 occurrence contracts bind reviewed executor revisions."""

import pytest

from executors.campaign_bootstrap import bootstrap_campaign_executors
from executors.executor_registry import registry
from executors.registry_initializer import initialize_registry
from runners.capability_facts import FactScope
from runners.c0026_runtime_contracts import load_c0026_runtime_contracts


def scope():
    return FactScope(
        run_id="run-a",
        environment_id="lab-a",
        epoch="boot-a",
        locus="target",
        host_id="target-linux-1",
        principal="ubuntu",
    )


def load():
    initialize_registry()
    bootstrap_campaign_executors("0.c0026")
    return load_c0026_runtime_contracts(scope(), registry)


def test_exact_selected_population_and_measured_dependencies():
    contracts = load()
    assert [item.technique_id for item in contracts] == [
        "T1583.001",
        "T1568",
        "T1105",
        "T1005",
        "T1560.001",
        "T1030",
    ]
    assert [item.occurrence for item in contracts] == [1, 2, 3, 4, 5, 6]
    assert contracts[0].mode == "naive_simulated"
    assert contracts[0].observers == ()
    assert contracts[0].scope.locus == "controller"
    assert [item.name for item in contracts[4].requirements] == [
        "lab:shell",
        "collection:verified",
    ]
    assert [item.name for item in contracts[5].requirements] == [
        "lab:shell",
        "archive:verified",
    ]
    assert [item.name for item in contracts[2].requirements] == ["lab:shell"]
    assert contracts[1].observers == ("c0026-resolution",)


def test_boot_scope_cannot_be_bound_to_another_principal():
    wrong = FactScope(**(scope().model_dump() | {"principal": "vagrant"}))
    with pytest.raises(ValueError):
        load_c0026_runtime_contracts(wrong, registry)


def test_selected_executor_identity_drift_is_refused(monkeypatch):
    initialize_registry()
    bootstrap_campaign_executors("0.c0026")
    original = registry.get_executor

    def replacement(campaign_id, sut_profile_id):
        return True, "", "", []

    monkeypatch.setattr(
        registry,
        "get_executor",
        lambda technique, campaign=None: (
            replacement if technique == "T1005" else original(technique, campaign)
        ),
    )
    with pytest.raises(ValueError):
        load_c0026_runtime_contracts(scope(), registry)
