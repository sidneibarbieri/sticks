from pathlib import Path
import socket
import subprocess

from executors import shadowray_fixed_executors as shadowray
from scripts.probe_shadowray_target import measure_transfer


def test_shadowray_transfer_uses_target_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)

    def reject_operator(*args, **kwargs):
        raise AssertionError("Operator execution is forbidden")

    monkeypatch.setattr(subprocess, "run", reject_operator)
    monkeypatch.setattr(
        shadowray,
        "run_bash_on_target_vm",
        lambda **kwargs: subprocess.CompletedProcess(
            [], 0, "[transfer-target] target-linux-1", ""
        ),
    )
    success, stdout, _, artifacts = shadowray.execute_t1105_shadowray_fixed(
        "0.shadowray", "0.shadowray"
    )
    assert success
    assert "[transfer-target]" in stdout
    assert Path(artifacts[0]).is_file()
    assert not Path("data/artifacts/network_tool.sh").exists()


def test_other_campaign_dispatch_is_preserved(monkeypatch):
    expected = (True, "other target", "", ["other artifact"])

    def other_campaign(campaign_id, sut_profile_id, **kwargs):
        assert (campaign_id, sut_profile_id, kwargs) == (
            "0.outer_space",
            "0.outer_space",
            {"reviewer": True},
        )
        return expected

    monkeypatch.setattr(shadowray, "execute_t1105_real", other_campaign)
    assert (
        shadowray.execute_t1105_shadowray_fixed(
            "0.outer_space",
            "0.outer_space",
            reviewer=True,
        )
        == expected
    )


def test_transport_failure_is_not_operator_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    monkeypatch.setattr(
        shadowray,
        "run_bash_on_target_vm",
        lambda **kwargs: subprocess.CompletedProcess([], 7, "", "guest unavailable"),
    )
    success, _, stderr, artifacts = shadowray.execute_t1105_shadowray_fixed(
        "0.shadowray", "0.shadowray"
    )
    assert not success
    assert stderr == "guest unavailable"
    assert Path(artifacts[0]).read_text().endswith("guest unavailable")


def test_exit_zero_without_observation_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    monkeypatch.setattr(
        shadowray,
        "run_bash_on_target_vm",
        lambda **kwargs: subprocess.CompletedProcess([], 0, "", ""),
    )
    success, _, stderr, _ = shadowray.execute_t1105_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )
    assert not success
    assert "observation missing" in stderr


def test_controlled_http_transfer_matches_declared_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    guest_workspace = tmp_path / "sticks-shadowray-transfer"
    guest_log = tmp_path / "sticks-shadowray-http.log"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    def guest_transport(**kwargs):
        assert kwargs["execution_user"] == "rayuser"
        script = (
            kwargs["bash_script"]
            .replace("/tmp/sticks-shadowray-transfer", str(guest_workspace))
            .replace("/tmp/sticks-shadowray-http.log", str(guest_log))
            .replace("18080", str(port))
        )
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", guest_transport)
    success, stdout, _, _ = shadowray.execute_t1105_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )
    assert success
    assert "[transfer-target]" in stdout
    assert (guest_workspace / "downloaded_tool.sh").read_bytes() == (
        guest_workspace / "source/network_tool.sh"
    ).read_bytes()
    assert measure_transfer(tmp_path)["passed"]
    (guest_workspace / "downloaded_tool.sh").chmod(0o644)
    assert not measure_transfer(tmp_path)["passed"]
    assert '"GET /network_tool.sh HTTP/1.1" 200' in guest_log.read_text()
