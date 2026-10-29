from __future__ import annotations

import json
import tarfile
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from scripts import package_prepared_c0045_role as package


def test_role_disk_rejects_missing_overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(package, "PROJECT_ROOT", tmp_path)

    with pytest.raises(ValueError, match="Expected one prepared caldera overlay"):
        package._role_disk("caldera")


def test_role_disk_rejects_ambiguous_overlays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine_root = tmp_path / "lab/vagrant/caldera/.vagrant/machines/caldera/qemu"
    for suffix in ("first", "second"):
        disk = machine_root / suffix / "linked-box.img"
        disk.parent.mkdir(parents=True, exist_ok=True)
        disk.write_bytes(b"qcow")
    monkeypatch.setattr(package, "PROJECT_ROOT", tmp_path)

    with pytest.raises(ValueError, match="found 2"):
        package._role_disk("caldera")


@pytest.mark.parametrize("state", ("poweroff", "stopped"))
def test_require_halted_accepts_provider_halted_states(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    monkeypatch.setattr(
        package.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0], returncode=0, stdout=f"1,default,state,{state}\n", stderr=""
        ),
    )

    package._require_halted("caldera")


def test_require_halted_rejects_running_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        package.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0], returncode=0, stdout="1,default,state,running\n", stderr=""
        ),
    )

    with pytest.raises(RuntimeError, match="must be halted"):
        package._require_halted("caldera")


def test_package_role_publishes_complete_archive_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_disk = tmp_path / "source.img"
    source_disk.write_bytes(b"source")
    monkeypatch.setattr(package, "_require_halted", lambda role: None)
    monkeypatch.setattr(package, "_role_disk", lambda role: source_disk)

    def fake_qemu_convert(command: list[str], check: bool) -> CompletedProcess[str]:
        Path(command[-1]).write_bytes(source_disk.read_bytes())
        return CompletedProcess(args=command, returncode=0)

    monkeypatch.setattr(package.subprocess, "run", fake_qemu_convert)
    output = package.package_role("caldera", tmp_path / "boxes")

    assert output.exists()
    with tarfile.open(output) as archive:
        assert archive.getnames() == ["metadata.json", "Vagrantfile", "box.img"]
        metadata = json.load(archive.extractfile("metadata.json"))
    assert metadata == {"format": "qcow2", "provider": "libvirt"}
