"""Enrollment must bind the operation to a stable fresh target boot."""

import pytest

from scripts import prepare_caldera_session as preparation


@pytest.mark.parametrize("rebooted", [False, True])
def test_session_records_stable_boot_or_refuses_before_operation(tmp_path, monkeypatch, rebooted):
    boots = iter([
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002" if rebooted else "00000000-0000-0000-0000-000000000001",
    ])
    operations = []

    def guest(lab, role, command):
        if role == "caldera":
            return "b24f6e7a99cab19cbf417009bda9b9c6c81abc31"
        return next(boots)

    def request(method, path, payload):
        operations.append(payload)
        return {"id": "operation"}

    monkeypatch.setattr(preparation, "ARTIFACT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(preparation, "guest_command", guest)
    monkeypatch.setattr(preparation, "laboratory_transport", lambda _: request)
    monkeypatch.setattr(preparation, "deploy_agent", lambda *_: None)
    monkeypatch.setattr(preparation, "wait_for_agent", lambda *_: "agent")
    output = tmp_path / "session.json"
    if rebooted:
        with pytest.raises(ValueError, match="rebooted"):
            preparation.prepare_session(tmp_path, output)
        assert not output.exists()
        assert operations == []
    else:
        session = preparation.prepare_session(tmp_path, output)
        assert session.binding.agent_id == "agent"
        assert str(session.target_boot_id).endswith("0001")
        assert output.exists()
        assert len(operations) == 1


def test_existing_session_refuses_before_lab_access(tmp_path, monkeypatch):
    output = tmp_path / "session.json"
    output.write_text("{}")
    monkeypatch.setattr(preparation, "guest_command", lambda *_: pytest.fail("must not contact lab"))
    with pytest.raises(FileExistsError):
        preparation.prepare_session(tmp_path, output)


def test_session_records_laboratory_relative_to_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, "ARTIFACT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(preparation, "guest_command", lambda lab, role, command: (
        "b24f6e7a99cab19cbf417009bda9b9c6c81abc31" if role == "caldera"
        else "00000000-0000-0000-0000-000000000001"))
    monkeypatch.setattr(preparation, "laboratory_transport", lambda _: lambda *a: {"id": "op"})
    monkeypatch.setattr(preparation, "deploy_agent", lambda *_: None)
    monkeypatch.setattr(preparation, "wait_for_agent", lambda *_: "agent")
    lab = tmp_path / "lab" / "vagrant"
    lab.mkdir(parents=True)
    output = tmp_path / "evidence" / "session.json"
    session = preparation.prepare_session(lab, output)
    assert str(session.lab_root) == "lab/vagrant"
    assert str(tmp_path) not in output.read_text()


def test_session_refuses_laboratory_outside_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, "ARTIFACT_ROOT", (tmp_path / "artifact").resolve())
    monkeypatch.setattr(preparation, "guest_command", lambda *_: pytest.fail("must not contact lab"))
    with pytest.raises(ValueError, match="inside the artifact root"):
        preparation.prepare_session(tmp_path / "elsewhere", tmp_path / "session.json")
