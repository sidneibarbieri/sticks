"""Enrollment preserves the declared principal through trust changes."""
import pytest
from pydantic import ValidationError
from runners import caldera_lab_bootstrap as bootstrap


@pytest.mark.parametrize("principal", ["ubuntu", "rayuser"])
def test_deployment_uses_declared_principal(tmp_path, monkeypatch, principal):
    commands = []
    def guest(lab_root, host, command, *, timeout=60):
        commands.append((host, command))
        return "aarch64" if command == "uname -m" else ""
    monkeypatch.setattr(bootstrap, "guest_command", guest)
    identity = bootstrap.CalderaAgentIdentity(principal=principal)
    bootstrap.deploy_agent(tmp_path, "group", "/tmp/group", identity=identity)
    assert len(commands) == 3
    assert all(host == identity.host for host, _ in commands)
    assert all(command.startswith(f"sudo -n -H -u {principal} /bin/bash -lc ")
               for _, command in commands[1:])


@pytest.mark.parametrize("drift_after_trust", [False, True])
def test_wrong_principal_is_rejected_even_after_trust(drift_after_trust):
    requests = []
    reads = 0
    def transport(method, path, payload):
        nonlocal reads
        requests.append((method, path, payload))
        if method != "GET":
            return None
        reads += 1
        return [{
            "paw": "agent", "group": "group", "host": "target-linux-1",
            "username": "rayuser" if drift_after_trust and reads == 1 else "ubuntu",
            "platform": "linux", "executors": ["sh"], "trusted": reads > 1,
        }]
    identity = bootstrap.CalderaAgentIdentity(principal="rayuser")
    with pytest.raises(ValueError, match="principal"):
        bootstrap.wait_for_agent(transport, "group", identity=identity)
    if not drift_after_trust:
        assert requests == [("GET", "/agents", None)]


@pytest.mark.parametrize("principal", ["", "-root", "rayuser;id", "ray user"])
def test_invalid_principal_refuses_before_bootstrap(principal):
    with pytest.raises(ValidationError):
        bootstrap.CalderaAgentIdentity(principal=principal)
