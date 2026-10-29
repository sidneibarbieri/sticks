"""Reject successful-looking links that differ from the declared dispatch."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from adapters.caldera_dispatch import (
    CalderaDispatchExpectation,
    CalderaDispatchIntent,
    command_digest,
    verify_completed_dispatch,
)
from adapters.caldera_operations import CalderaOperations


@pytest.fixture
def expectation():
    return CalderaDispatchExpectation(
        operation_id="operation-one", link_id="link-one", group="isolated-run",
        agent_id="agent-one", host="target-one", principal="ubuntu",
        platform="linux", executor="sh", command_sha256=command_digest("printf test"),
    )


@pytest.fixture
def operation():
    return {
        "id": "operation-one", "group": "isolated-run", "state": "running",
        "obfuscator": "plain-text",
        "host_group": [{
            "paw": "agent-one", "group": "isolated-run", "host": "target-one",
            "username": "ubuntu", "platform": "linux", "trusted": True,
            "executors": ["sh"],
        }],
        "chain": [{
            "id": "link-one", "paw": "agent-one", "host": "target-one",
            "command": "printf test", "plaintext_command": "printf test",
            "executor": {"name": "sh", "platform": "linux", "timeout": 30},
            "status": 0, "finish": "2026-10-28T12:00:00Z",
        }],
    }


def test_native_completion_is_a_receipt_not_an_effect(expectation, operation):
    receipt = verify_completed_dispatch(expectation, operation)
    assert receipt.assurance == "native_command_completed"
    assert receipt.model_dump(exclude={"assurance", "finished_at", "schema_version"}) == expectation.model_dump()
    assert "command" not in receipt.model_dump()
    assert "effect_observed" not in receipt.model_dump()


def test_intent_is_frozen_before_the_native_link_exists(expectation):
    intent = CalderaDispatchIntent(**expectation.model_dump(exclude={"link_id"}))
    assert "link_id" not in intent.model_dump()
    assert intent.bind_link("link-one") == expectation
    with pytest.raises(ValidationError):
        intent.host = "other-target"


@pytest.mark.parametrize("status", [False, True, "0", 0.0, None])
def test_completion_status_cannot_be_coerced(expectation, operation, status):
    operation["chain"][0]["status"] = status
    with pytest.raises(ValidationError):
        verify_completed_dispatch(expectation, operation)


@pytest.mark.parametrize("path,value,condition", [
    (("id",), "other-operation", "operation_identity"),
    (("group",), "other-group", "operation_group"),
    (("state",), "paused", "operation_state"),
    (("obfuscator",), "other", "plain_command_policy"),
    (("chain", 0, "paw"), "other-agent", "agent_identity"),
    (("chain", 0, "host"), "other-target", "target_identity"),
    (("host_group", 0, "group"), "other-group", "agent_group"),
    (("host_group", 0, "username"), "root", "principal"),
    (("host_group", 0, "trusted"), False, "agent_trusted"),
    (("host_group", 0, "platform"), "windows", "platform"),
    (("host_group", 0, "executors"), [], "executor"),
    (("chain", 0, "executor", "name"), "other", "executor"),
    (("chain", 0, "executor", "timeout"), 31, "executor_timeout"),
    (("chain", 0, "command"), "sensitive-test-command", "command_digest"),
    (("chain", 0, "plaintext_command"), "printf test\n", "plaintext_digest"),
    (("chain", 0, "status"), 1, "completion_status"),
    (("chain", 0, "finish"), None, "finish_timestamp"),
    (("chain", 0, "finish"), "  ", "finish_timestamp"),
])
def test_wrong_dispatch_is_rejected(expectation, operation, path, value, condition):
    target = operation
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(ValueError, match=condition) as error:
        verify_completed_dispatch(expectation, operation)
    assert "sensitive-test-command" not in str(error.value)
    assert "other-operation" not in str(error.value)


@pytest.mark.parametrize("field,condition", [("chain", "unique_link"), ("host_group", "unique_agent")])
def test_duplicate_identity_is_ambiguous(expectation, operation, field, condition):
    operation[field].append(deepcopy(operation[field][0]))
    with pytest.raises(ValueError, match=condition):
        verify_completed_dispatch(expectation, operation)


def test_all_failed_conditions_are_named(expectation, operation):
    operation["chain"][0]["status"] = 2
    operation["host_group"][0]["username"] = "root"
    with pytest.raises(ValueError) as error:
        verify_completed_dispatch(expectation, operation)
    assert "principal" in str(error.value)
    assert "completion_status" in str(error.value)


def test_client_reads_native_operation_before_returning_receipt(expectation, operation):
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        return operation

    receipt = CalderaOperations(transport).completed_dispatch(expectation)
    assert receipt.link_id == "link-one"
    assert calls == [("GET", "/operations/operation-one", None)]


def test_native_read_failure_propagates(expectation):
    def unavailable_transport(method, path, payload):
        raise TimeoutError("native operation unavailable")

    with pytest.raises(TimeoutError, match="native operation unavailable"):
        CalderaOperations(unavailable_transport).completed_dispatch(expectation)


@pytest.mark.parametrize("status", [False, True, "0", 0.0, None])
def test_link_polling_rejects_noninteger_status(status):
    client = CalderaOperations(lambda method, path, payload: {
        "id": "link-one", "status": status, "finish": "timestamp",
    })
    with pytest.raises(ValueError, match="status must be an integer"):
        client.link("operation-one", "link-one")


def test_native_timeout_cannot_be_a_boolean(expectation, operation):
    operation["chain"][0]["executor"]["timeout"] = True
    with pytest.raises(ValidationError):
        verify_completed_dispatch(expectation, operation)
