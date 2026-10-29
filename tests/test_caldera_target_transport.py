"""Check executor routing and refusal without SSH fallback."""

import subprocess
from types import SimpleNamespace

import pytest

from adapters.caldera_dispatch import CalderaDispatchIntent, command_digest
from adapters.caldera_operations import CalderaOperations
from executors import lab_transport
from executors.lab_transport import TargetCommand, target_command_transport, target_executor_dispatch
from runners import caldera_target_transport
from runners.caldera_target_transport import CalderaTargetTransport, encode_target_command


def binding():
    return CalderaDispatchIntent(
        operation_id="operation", group="isolated", agent_id="agent",
        host="target-linux-1", principal="ubuntu", platform="linux", executor="sh",
        command_sha256=command_digest("initial"),
    )


def test_target_scripts_route_to_caldera_and_retain_submission(tmp_path, monkeypatch):
    calls = []

    def native(method, path, payload):
        calls.append((method, path, payload))
        return {"id": "link", "status": 0, "finish": "timestamp"}

    monkeypatch.setattr(caldera_target_transport, "retain_completed_command",
                        lambda *_: SimpleNamespace(process_exit_code=0, stdout="observed", stderr=""))
    transport = CalderaTargetTransport(CalderaOperations(native), binding(), tmp_path / "journal")
    monkeypatch.setattr(lab_transport, "resolve_target_vm_name", lambda _: "target-linux-1")
    monkeypatch.setattr(lab_transport, "run_command_in_vm", lambda **_: pytest.fail("SSH fallback"))
    with target_command_transport(transport), target_executor_dispatch():
        result = lab_transport.run_bash_on_target_vm("0.c0026", "printf observed", execution_user="ubuntu")
    assert result.stdout == "observed"
    assert calls[0][2]["executor"]["command"].startswith("python3 -c")
    assert (tmp_path / "journal/command-0001/dispatch-submission.json").exists()


@pytest.mark.parametrize("host,principal", [("attacker", "ubuntu"), ("target-linux-1", "root"), ("target-linux-1", None)])
def test_agent_scope_mismatch_refuses_before_submission(tmp_path, host, principal):
    client = CalderaOperations(lambda *_: pytest.fail("must not send"))
    transport = CalderaTargetTransport(client, binding(), tmp_path / "journal")
    with pytest.raises(ValueError, match="agent scope"):
        transport(TargetCommand(host, "printf observed", 30, principal))
    assert list((tmp_path / "journal").iterdir()) == []


def test_transport_failure_restores_context_without_fallback(monkeypatch):
    monkeypatch.setattr(lab_transport, "resolve_target_vm_name", lambda _: "target-linux-1")
    monkeypatch.setattr(lab_transport, "run_command_in_vm", lambda **_: subprocess.CompletedProcess([], 0, "ssh", ""))

    def unavailable(request):
        raise TimeoutError("native unavailable")

    with pytest.raises(TimeoutError, match="native unavailable"):
        with target_command_transport(unavailable), target_executor_dispatch():
            lab_transport.run_bash_on_target_vm("0.c0026", "true", execution_user="ubuntu")
    assert lab_transport.run_bash_on_target_vm("0.c0026", "true").stdout == "ssh"


def test_probe_does_not_use_caldera_even_inside_campaign_session(monkeypatch):
    monkeypatch.setattr(lab_transport, "resolve_target_vm_name", lambda _: "target-linux-1")
    monkeypatch.setattr(lab_transport, "run_command_in_vm", lambda **_: subprocess.CompletedProcess([], 0, "probe", ""))
    with target_command_transport(lambda _: pytest.fail("probe routed to CALDERA")):
        assert lab_transport.run_bash_on_target_vm("0.c0026", "hostname").stdout == "probe"


def test_native_newline_stripping_preserves_multiline_script():
    import shlex
    script = "set -eu\nprintf '%s\\n' 'first'\nprintf '%s\\n' 'second'\n"
    original = "bash -lc " + shlex.quote(script)
    encoded = encode_target_command(original)
    assert "\n" not in encoded
    result = subprocess.run(encoded.replace("\n", ""), shell=True, check=True,
                            capture_output=True, text=True)
    assert result.stdout == "first\nsecond\n"
