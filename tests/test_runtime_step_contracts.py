"""Selected runtime contracts enforce scoped assurance, not technique-name trust."""

import hashlib
import importlib.util

import pytest
from pydantic import ValidationError

from runners.capability_facts import CapabilityFact, CapabilityRequirement, FactScope
from runners.capability_store import CapabilityStore
from runners.runtime_step_contracts import (
    RuntimeStepContract,
    unmet_requirements,
    verify_executor_binding,
)


def scope(**changes):
    return FactScope(
        **(
            dict(
                run_id="run-a",
                environment_id="lab-a",
                epoch="boot-a",
                locus="target",
                host_id="target-a",
                principal="ubuntu",
            )
            | changes
        )
    )


def required(origins=frozenset({"observed"}), **changes):
    return CapabilityRequirement(
        name="lab:shell", scope=scope(**changes), accepted_origins=origins
    )


def contract(**changes):
    fields = dict(
        campaign_id="0.c0026",
        occurrence=1,
        technique_id="T1005",
        executor_id="executors.collection.execute",
        executor_sha256="a" * 64,
        mode="real_controlled",
        scope=scope(),
        requirements=(required(),),
        observers=(),
    )
    return RuntimeStepContract(**(fields | changes))


@pytest.mark.parametrize("origin", ["profile_declaration", "simulation"])
def test_controlled_contract_rejects_nonobserved_requirement(origin):
    with pytest.raises(ValidationError):
        contract(requirements=(required(frozenset({origin})),))


def test_simulation_contract_can_explicitly_accept_simulation_state():
    simulated = contract(
        mode="naive_simulated", requirements=(required(frozenset({"simulation"})),)
    )
    assert simulated.mode == "naive_simulated"


def test_requirement_cannot_belong_to_another_run():
    with pytest.raises(ValidationError):
        contract(requirements=(required(run_id="old-run"),))


def test_requirement_cannot_belong_to_another_environment():
    with pytest.raises(ValidationError):
        contract(requirements=(required(environment_id="other-lab"),))


def test_declaration_does_not_satisfy_controlled_step():
    store = CapabilityStore()
    store.add_declaration(
        CapabilityFact(
            name="lab:shell",
            origin="profile_declaration",
            scope=scope(),
            producer_occurrence=None,
            observation=None,
        )
    )
    assert unmet_requirements(contract(), store) == (required(),)


def test_simulation_step_consumes_only_permitted_matching_state():
    store = CapabilityStore()
    simulated = CapabilityFact(
        name="lab:shell",
        origin="simulation",
        scope=scope(),
        producer_occurrence=None,
        observation=None,
    )
    store.add_simulation(simulated)
    allowed = contract(
        mode="naive_simulated", requirements=(required(frozenset({"simulation"})),)
    )
    assert unmet_requirements(allowed, store) == ()
    assert unmet_requirements(contract(), store) == (required(),)


@pytest.mark.parametrize(
    "field,value",
    [
        ("occurrence", 0),
        ("executor_sha256", "bad"),
        ("executor_id", ""),
        ("mode", "unknown"),
    ],
)
def test_contract_rejects_unbound_or_unknown_execution(field, value):
    with pytest.raises(ValidationError):
        contract(**{field: value})


def test_unknown_observer_cannot_be_loaded_from_contract():
    with pytest.raises(ValidationError):
        contract(observers=("proposer.callback",))


def test_duplicate_requirements_are_rejected():
    with pytest.raises(ValidationError):
        contract(requirements=(required(), required()))


def selected_executor(tmp_path):
    source = tmp_path / "selected.py"
    content = b"def execute():\n    return 'completed'\n"
    source.write_bytes(content)
    spec = importlib.util.spec_from_file_location("contract_test_executor", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bound = contract(
        executor_id="contract_test_executor.execute",
        executor_sha256=hashlib.sha256(content).hexdigest(),
    )
    return bound, module.execute, source


def test_selected_executor_matches_identity_and_actual_source(tmp_path):
    bound, executor, _ = selected_executor(tmp_path)
    verify_executor_binding(bound, executor)


def test_changed_executor_source_is_refused(tmp_path):
    bound, executor, source = selected_executor(tmp_path)
    source.write_bytes(b"def execute():\n    return 'different'\n")
    with pytest.raises(ValueError):
        verify_executor_binding(bound, executor)


def test_other_executor_identity_is_refused(tmp_path):
    bound, executor, _ = selected_executor(tmp_path)
    wrong = RuntimeStepContract(
        **(bound.model_dump() | {"executor_id": "other.execute"})
    )
    with pytest.raises(ValueError):
        verify_executor_binding(wrong, executor)
