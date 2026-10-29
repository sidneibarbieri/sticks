"""The laboratory provisioner must not put credentials in its run log."""

from pathlib import Path

from src import apply_sut_profile


def test_weak_credential_success_log_omits_password(monkeypatch, tmp_path: Path):
    messages: list[str] = []

    def fake_ssh_command(*args, **kwargs):
        return True, "", ""

    monkeypatch.setattr(apply_sut_profile, "execute_ssh_command", fake_ssh_command)
    monkeypatch.setattr(apply_sut_profile, "log_info", messages.append)

    applied = apply_sut_profile.apply_weak_credentials(
        host_ip="192.168.56.30",
        weakness={"username": "fixture_user", "password": "unique-secret-do-not-log"},
        provider="qemu",
        vm_name="target-linux-1",
        base_dir=tmp_path,
    )

    assert applied
    assert any("fixture_user" in message for message in messages)
    assert all("unique-secret-do-not-log" not in message for message in messages)


def test_weak_credential_failure_keeps_error_without_password(monkeypatch, tmp_path: Path):
    messages: list[str] = []

    def fake_ssh_command(*args, **kwargs):
        return False, "", "rejected unique-secret-do-not-log by target"

    monkeypatch.setattr(apply_sut_profile, "execute_ssh_command", fake_ssh_command)
    monkeypatch.setattr(apply_sut_profile, "log_info", lambda message: None)
    monkeypatch.setattr(apply_sut_profile, "log_error", messages.append)

    applied = apply_sut_profile.apply_weak_credentials(
        host_ip="192.168.56.30",
        weakness={"username": "fixture_user", "password": "unique-secret-do-not-log"},
        provider="qemu",
        vm_name="target-linux-1",
        base_dir=tmp_path,
    )

    assert not applied
    assert len(messages) == 1
    assert "rejected" in messages[0]
    assert "unique-secret-do-not-log" not in messages[0]
