"""Exercise legacy infrastructure paths without invoking external providers."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ARTIFACT_ROOT = Path(__file__).resolve().parents[1]


def load_copied_script(tmp_path, monkeypatch, filename):
    script = tmp_path / "artifact/measurement/sut/scripts" / filename
    script.parent.mkdir(parents=True)
    shutil.copyfile(ARTIFACT_ROOT / "measurement/sut/scripts" / filename, script)
    name = "legacy_infra_" + script.stem
    specification = importlib.util.spec_from_file_location(name, script)
    module = importlib.util.module_from_spec(specification)
    monkeypatch.setitem(sys.modules, name, module)
    specification.loader.exec_module(module)
    return module, tmp_path / "artifact"


def test_legacy_provisioner_uses_copied_artifact_root(tmp_path, monkeypatch):
    module, artifact = load_copied_script(tmp_path, monkeypatch, "automated_campaign_runner.py")
    monkeypatch.setattr(module.CalderaClient, "is_healthy", lambda self: False)
    calls = []

    def reject_provisioning(command, **kwargs):
        calls.append((command, kwargs["cwd"]))
        return subprocess.CompletedProcess(command, 1, "", "controlled refusal")

    monkeypatch.setattr(module.subprocess, "run", reject_provisioning)

    assert module.SUTProvisioner(module.CampaignRequirements()).provision() is False
    assert calls == [
        (["docker", "compose", "-f", str(artifact / "measurement/sut/docker-compose.multi-host.yml"),
          "up", "-d"], str(artifact))
    ]


def test_legacy_vagrant_teardown_uses_copied_artifact_root(tmp_path, monkeypatch):
    pytest.importorskip("requests", reason="legacy HTTP integration dependency")
    module, artifact = load_copied_script(tmp_path, monkeypatch, "run_full_pipeline.py")
    calls = []

    def accept_teardown(command, **kwargs):
        calls.append((command, kwargs["cwd"]))
        assert kwargs["check"] is True
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", accept_teardown)

    assert module.InfrastructureManager("vagrant").stop() is True
    assert calls == [(["vagrant", "destroy", "-f"], artifact / "measurement/sut")]


@pytest.mark.parametrize("operation", ["start", "stop"])
@pytest.mark.parametrize("provider_fails", [False, True])
def test_vagrant_operation_does_not_change_process_directory(
    tmp_path, monkeypatch, operation, provider_fails
):
    pytest.importorskip("requests", reason="legacy HTTP integration dependency")
    module, artifact = load_copied_script(tmp_path, monkeypatch, "run_full_pipeline.py")
    (artifact / "measurement/sut/Vagrantfile").write_text("# controlled test input\n")
    monkeypatch.chdir(tmp_path)
    original_directory = Path.cwd()
    calls = []

    def provider_result(command, **kwargs):
        calls.append((command, kwargs))
        if provider_fails:
            raise subprocess.CalledProcessError(1, command, stderr=b"controlled refusal")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(module.subprocess, "run", provider_result)

    assert getattr(module.InfrastructureManager("vagrant"), operation)() is not provider_fails
    assert Path.cwd() == original_directory
    assert len(calls) == 1
    assert calls[0][1]["cwd"] == artifact / "measurement/sut"
