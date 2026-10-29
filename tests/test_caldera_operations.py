"""Check native operation requests and malformed response rejection."""

import pytest
from pydantic import SecretStr

from adapters.caldera_operations import CalderaCommand, CalderaOperations, http_transport


def test_native_incremental_operation_contract() -> None:
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        if path.endswith("/potential-links"):
            return {"id": "link-one"}
        if method == "GET":
            return {"id": "link-one", "status": 0, "finish": "timestamp"}
        return {"id": "operation-one"}

    client = CalderaOperations(transport)
    operation = client.create_operation("conformance", "isolated-test-group")
    link = client.submit_command(
        operation, CalderaCommand(agent_id="test-agent", platform="linux", executor="sh", command="printf test")
    )
    assert client.link(operation, link)["status"] == 0
    client.finish_operation(operation)
    assert calls[0][2]["auto_close"] is False
    assert calls[0][2]["group"] == "isolated-test-group"
    assert calls[1][1] == "/operations/operation-one/potential-links"
    assert calls[1][2]["paw"] == "test-agent"
    assert calls[1][2]["executor"]["platform"] == "linux"
    assert calls[-1] == ("PATCH", "/operations/operation-one", {"state": "finished"})


@pytest.mark.parametrize("response", [None, [], {}, {"id": 5}, {"id": ""}])
def test_missing_operation_identity_is_an_error(response) -> None:
    client = CalderaOperations(lambda method, path, payload: response)
    with pytest.raises(ValueError, match="operation identity"):
        client.create_operation("conformance", "isolated-test-group")


def test_empty_group_cannot_select_all_agents() -> None:
    def unexpected_transport(method, path, payload):
        pytest.fail("an unscoped operation must not reach CALDERA")

    with pytest.raises(ValueError, match="isolated agent group"):
        CalderaOperations(unexpected_transport).create_operation("conformance", " ")


def test_reading_another_link_is_an_error() -> None:
    client = CalderaOperations(lambda method, path, payload: {"id": "wrong-link"})
    with pytest.raises(ValueError, match="identity differs"):
        client.link("operation", "expected-link")


def test_transport_failure_is_not_reported_as_completion() -> None:
    def failing_transport(method, path, payload):
        raise TimeoutError("API unavailable")

    with pytest.raises(TimeoutError, match="API unavailable"):
        CalderaOperations(failing_transport).create_operation("conformance", "isolated-test-group")


@pytest.mark.parametrize("url", ["file:///tmp/service", "http://user:secret@localhost", "http://localhost/other"])
def test_http_transport_rejects_ambiguous_origin(url) -> None:
    with pytest.raises(ValueError):
        http_transport(url, SecretStr("test-only"))
