"""Check durable intent ordering and ambiguous network outcomes."""

import pytest

from adapters.caldera_dispatch import CalderaDispatchExpectation, CalderaDispatchIntent, command_digest
from adapters.caldera_operations import CalderaCommand, CalderaOperations
from runners.recorded_caldera_dispatch import submit_recorded_command
from runners.recorded_caldera_dispatch import retain_completed_command, replay_completed_command
from adapters.caldera_command_result import CalderaCommandResult
from adapters.caldera_dispatch import CalderaDispatchReceipt


@pytest.fixture
def intent():
    return CalderaDispatchIntent(
        operation_id="operation-one", group="isolated-run", agent_id="agent-one",
        host="target-one", principal="ubuntu", platform="linux", executor="sh",
        command_sha256=command_digest("printf test"),
    )


@pytest.fixture
def command():
    return CalderaCommand(agent_id="agent-one", platform="linux", executor="sh", command="printf test")


def test_intent_is_retained_before_the_only_submission(intent, command, tmp_path):
    output = tmp_path / "dispatch"
    calls = []

    def transport(method, path, payload):
        retained = CalderaDispatchIntent.model_validate_json((output / "dispatch-intent.json").read_bytes())
        assert retained == intent
        assert not (output / "dispatch-submission.json").exists()
        calls.append((method, path))
        return {"id": "link-one"}

    expected = submit_recorded_command(CalderaOperations(transport), intent, command, output)
    assert expected == intent.bind_link("link-one")
    retained = CalderaDispatchExpectation.model_validate_json((output / "dispatch-submission.json").read_bytes())
    assert retained == expected
    assert calls == [("POST", "/operations/operation-one/potential-links")]


def test_network_failure_preserves_intent_and_does_not_retry(intent, command, tmp_path):
    output = tmp_path / "dispatch"
    calls = []

    def unavailable(method, path, payload):
        calls.append(path)
        raise TimeoutError("submission acknowledgment unavailable")

    with pytest.raises(TimeoutError, match="acknowledgment unavailable"):
        submit_recorded_command(CalderaOperations(unavailable), intent, command, output)
    assert (output / "dispatch-intent.json").exists()
    assert not (output / "dispatch-submission.json").exists()
    assert len(calls) == 1


def test_completion_retains_verified_result_without_resubmission(intent, command, tmp_path, monkeypatch):
    client = CalderaOperations(lambda *args: {"id": "link-one"})
    output = tmp_path / "dispatch"
    expected = submit_recorded_command(client, intent, command, output)
    result = CalderaCommandResult(
        dispatch=CalderaDispatchReceipt(**expected.model_dump(), finished_at="timestamp"),
        stdout="test", stderr="", process_exit_code=0,
    )
    calls = []

    def complete(submitted):
        calls.append(submitted)
        return result

    monkeypatch.setattr(client, "completed_command", complete)
    assert retain_completed_command(client, output) == result
    assert CalderaCommandResult.model_validate_json(
        (output / "command-result.json").read_bytes()
    ) == result
    with pytest.raises(FileExistsError):
        retain_completed_command(client, output)
    assert calls == [expected]
    assert replay_completed_command(output) == result
    changed = result.model_copy(update={
        "dispatch": result.dispatch.model_copy(update={"agent_id": "different-agent"})
    })
    (output / "command-result.json").write_text(changed.model_dump_json())
    with pytest.raises(ValueError, match="acknowledged dispatch"):
        replay_completed_command(output)


def test_completion_rejects_tampered_acknowledgment(intent, command, tmp_path):
    client = CalderaOperations(lambda *args: {"id": "link-one"})
    output = tmp_path / "dispatch"
    expected = submit_recorded_command(client, intent, command, output)
    (output / "dispatch-submission.json").write_text(
        expected.model_copy(update={"agent_id": "other-agent"}).model_dump_json()
    )
    with pytest.raises(ValueError, match="durable intent"):
        retain_completed_command(client, output)
    assert not (output / "command-result.json").exists()


def test_completion_failure_retains_only_submission(intent, command, tmp_path, monkeypatch):
    client = CalderaOperations(lambda *args: {"id": "link-one"})
    output = tmp_path / "dispatch"
    submit_recorded_command(client, intent, command, output)

    def unavailable(expected):
        raise TimeoutError("result unavailable")

    monkeypatch.setattr(client, "completed_command", unavailable)
    with pytest.raises(TimeoutError, match="result unavailable"):
        retain_completed_command(client, output)
    assert (output / "dispatch-submission.json").exists()
    assert not (output / "command-result.json").exists()


def test_reused_journal_refuses_submission(intent, command, tmp_path):
    def forbidden(method, path, payload):
        pytest.fail("reusing a journal must not send another command")

    with pytest.raises(FileExistsError):
        submit_recorded_command(CalderaOperations(forbidden), intent, command, tmp_path)


@pytest.mark.parametrize("field,value", [
    ("agent_id", "other-agent"), ("platform", "windows"),
    ("executor", "other"), ("command", "printf changed"),
    ("timeout_seconds", 31),
])
def test_mismatched_command_is_rejected_before_io(intent, command, tmp_path, field, value):
    output = tmp_path / "dispatch"
    changed = CalderaCommand.model_validate({**command.model_dump(), field: value})

    def forbidden(method, path, payload):
        pytest.fail("a mismatched command must not reach CALDERA")

    with pytest.raises(ValueError, match="submission conditions failed"):
        submit_recorded_command(CalderaOperations(forbidden), intent, changed, output)
    assert not output.exists()
