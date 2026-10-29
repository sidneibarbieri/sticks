"""Check native output identity, decoding failures and unknown legacy exit codes."""

import base64
from copy import deepcopy
import json

import pytest

from adapters.caldera_command_result import verify_completed_result
from adapters.caldera_dispatch import CalderaDispatchExpectation, command_digest
from adapters.caldera_operations import CalderaOperations


def encoded_output(stdout="output", stderr="", exit_code=0):
    payload = json.dumps({"stdout": stdout, "stderr": stderr, "exit_code": exit_code})
    return base64.b64encode(payload.encode()).decode()


@pytest.fixture
def expected():
    return CalderaDispatchExpectation(
        operation_id="operation", link_id="link", group="isolated", agent_id="agent",
        host="target", principal="ubuntu", platform="linux", executor="sh",
        command_sha256=command_digest("printf test"), timeout_seconds=30,
    )


@pytest.fixture
def native_operation():
    return {
        "id": "operation", "group": "isolated", "state": "finished", "obfuscator": "plain-text",
        "host_group": [{"paw": "agent", "group": "isolated", "host": "target", "username": "ubuntu",
                        "platform": "linux", "trusted": True, "executors": ["sh"]}],
        "chain": [{"id": "link", "paw": "agent", "host": "target", "command": "printf test",
                   "plaintext_command": "printf test", "executor": {"name": "sh", "platform": "linux", "timeout": 30},
                   "status": 0, "finish": "2026-10-28T12:00:00Z"}],
    }


@pytest.fixture
def native_result(native_operation):
    return {"link": deepcopy(native_operation["chain"][0]), "result": encoded_output()}


def test_native_output_is_bound_and_decoded(expected, native_operation, native_result):
    result = verify_completed_result(expected, native_operation, native_result)
    assert result.stdout == "output"
    assert result.stderr == ""
    assert result.process_exit_code == 0
    assert result.dispatch.link_id == expected.link_id


def test_missing_result_file_is_not_an_empty_success(expected, native_operation, native_result):
    native_result["result"] = ""
    with pytest.raises(ValueError):
        verify_completed_result(expected, native_operation, native_result)


def test_valid_empty_output_remains_distinct_from_missing_file(expected, native_operation, native_result):
    native_result["result"] = encoded_output(stdout="", exit_code="")
    result = verify_completed_result(expected, native_operation, native_result)
    assert result.stdout == ""
    assert result.process_exit_code is None


def test_native_string_zero_exit_is_normalized(expected, native_operation, native_result):
    native_result["result"] = encoded_output(exit_code="0")
    result = verify_completed_result(expected, native_operation, native_result)
    assert result.process_exit_code == 0


@pytest.mark.parametrize("field,value", [("paw", "other-agent"), ("command", "other-command"), ("finish", "other-finish")])
def test_result_for_another_link_snapshot_is_rejected(expected, native_operation, native_result, field, value):
    native_result["link"][field] = value
    with pytest.raises(ValueError, match="result link differs"):
        verify_completed_result(expected, native_operation, native_result)


@pytest.mark.parametrize("payload", ["not-base64", base64.b64encode(b"not JSON").decode(), base64.b64encode(b"\xff").decode()])
def test_malformed_output_is_not_replaced_with_blank_text(expected, native_operation, native_result, payload):
    native_result["result"] = payload
    with pytest.raises(ValueError):
        verify_completed_result(expected, native_operation, native_result)


@pytest.mark.parametrize("code", [False, "1", 1])
def test_ambiguous_or_failed_process_exit_is_rejected(expected, native_operation, native_result, code):
    native_result["result"] = encoded_output(exit_code=code)
    with pytest.raises(ValueError):
        verify_completed_result(expected, native_operation, native_result)


def test_client_reads_native_result_without_submitting_a_command(expected, native_operation, native_result):
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        return native_result if path.endswith("/result") else native_operation

    result = CalderaOperations(transport).completed_command(expected)
    assert result.stdout == "output"
    assert calls == [("GET", "/operations/operation", None), ("GET", "/operations/operation/links/link/result", None)]
