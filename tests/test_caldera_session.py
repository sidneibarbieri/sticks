"""Session selection must refuse missing credentials and unsupported campaigns."""

import json
from contextlib import contextmanager

import pytest

from adapters.caldera_dispatch import CalderaDispatchIntent, command_digest
from runners import caldera_session, campaign_runner


def test_session_requires_environment_key_before_creating_journal(tmp_path, monkeypatch):
    session = tmp_path / "session.json"
    session.write_text(json.dumps({
        "origin": "http://127.0.0.1:8888",
        "target_boot_id": "00000000-0000-0000-0000-000000000001",
        "binding": CalderaDispatchIntent(
            operation_id="operation", group="isolated", agent_id="agent",
            host="target-linux-1", principal="ubuntu", platform="linux", executor="sh",
            command_sha256=command_digest("placeholder"),
        ).model_dump(),
    }))
    monkeypatch.delenv("STICKS_CALDERA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="API_KEY"):
        with caldera_session.campaign_caldera_session(session, tmp_path / "journal"):
            pytest.fail("session must not activate")
    assert not (tmp_path / "journal").exists()


@pytest.mark.parametrize("stale", [False, True])
def test_boot_probe_is_challenge_bound(monkeypatch, stale):
    import subprocess
    session = caldera_session.CalderaSession(
        origin="http://127.0.0.1:8888",
        target_boot_id="00000000-0000-0000-0000-000000000001",
        binding=CalderaDispatchIntent(
            operation_id="operation", group="isolated", agent_id="agent",
            host="target-linux-1", principal="ubuntu", platform="linux", executor="sh",
            command_sha256=command_digest("placeholder"),
        ),
    )

    def probe(host, nonce):
        boot = "00000000-0000-0000-0000-000000000002" if stale else str(session.target_boot_id)
        return subprocess.CompletedProcess([], 0, f"{nonce}\t{host}\t{boot}\n", "")

    monkeypatch.setattr(caldera_session, "probe_vm_identity", probe)
    if stale:
        with pytest.raises(ValueError, match="current target boot"):
            caldera_session.require_session_boot(session)
    else:
        caldera_session.require_session_boot(session)


@pytest.mark.parametrize("campaign", ["0.c0010", "0.c0026"])
def test_runner_executes_campaign_inside_selected_session(tmp_path, monkeypatch, campaign):
    active = []

    @contextmanager
    def selected(session, journal):
        active.append((session, journal))
        yield
        active.clear()

    class Runner:
        def __init__(self, **kwargs):
            pass

        def run(self):
            assert len(active) == 1
            return type("Evidence", (), {"failed": 0})()

    monkeypatch.setattr(caldera_session, "campaign_caldera_session", selected)
    monkeypatch.setattr(campaign_runner, "UnifiedCampaignRunner", Runner)
    monkeypatch.setattr("sys.argv", ["run_campaign", "--campaign", campaign, "--require-lab",
                                     "--caldera-session", "session.json", "--output", str(tmp_path)])
    assert campaign_runner.main() == 0
    assert active == []


@pytest.mark.parametrize("arguments", [[], ["--all"], ["--campaign", "0.c0045", "--require-lab"]])
def test_runner_rejects_unsupported_session_selection(monkeypatch, arguments):
    monkeypatch.setattr("sys.argv", ["run_campaign", "--caldera-session", "session.json", *arguments])
    with pytest.raises(SystemExit) as error:
        campaign_runner.main()
    assert error.value.code == 2
