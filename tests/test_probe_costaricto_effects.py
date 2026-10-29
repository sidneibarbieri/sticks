"""Negative controls for the independent CostaRicto guest file predicates."""

import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


PROBE_PATH = Path(__file__).resolve().parents[1] / "scripts/probe_costaricto_effects.py"
SPEC = importlib.util.spec_from_file_location("costaricto_effect_probe", PROBE_PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def write_fixture(root: Path, relative: str, content: bytes, mode: int = 0o644) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)
    return path


def test_transfer_requires_matching_bytes_and_recorded_http_get(tmp_path):
    write_fixture(tmp_path, "tmp/sticks_t1105/payload.sh", probe.PAYLOAD)
    destination = write_fixture(
        tmp_path, "tmp/sticks_downloaded_payload.sh", probe.PAYLOAD, 0o755
    )
    log = write_fixture(
        tmp_path,
        "tmp/sticks_t1105_server.log",
        b'127.0.0.1 "GET /payload.sh HTTP/1.1" 200 -\n',
    )

    assert probe.measure_transfer(tmp_path)["passed"]
    log.write_text("server started\n")
    assert not probe.measure_transfer(tmp_path)["passed"]
    log.write_text('127.0.0.1 "GET /payload.sh HTTP/1.1" 200 -\n')
    destination.write_text("changed\n")
    assert not probe.measure_transfer(tmp_path)["passed"]


def test_transfer_rejects_missing_and_symlinked_destination(tmp_path):
    source = write_fixture(tmp_path, "tmp/sticks_t1105/payload.sh", probe.PAYLOAD)
    write_fixture(tmp_path, "tmp/sticks_t1105_server.log", b"log\n")
    with pytest.raises(FileNotFoundError):
        probe.measure_transfer(tmp_path)
    destination = tmp_path / "tmp/sticks_downloaded_payload.sh"
    destination.symlink_to(source)
    with pytest.raises(OSError):
        probe.measure_transfer(tmp_path)


def test_collection_requires_declared_source_copy_owner_and_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(
        probe.pwd, "getpwuid", lambda user_id: SimpleNamespace(pw_name="reconuser")
    )
    write_fixture(
        tmp_path, "home/reconuser/collection/finance_notes.txt", probe.COLLECTION
    )
    destination = write_fixture(
        tmp_path, "tmp/sticks_costaricto/local_collection.txt", probe.COLLECTION, 0o600
    )

    assert probe.measure_collection(tmp_path)["passed"]
    destination.chmod(0o644)
    assert not probe.measure_collection(tmp_path)["passed"]
    destination.chmod(0o600)
    destination.write_text("different\n")
    assert not probe.measure_collection(tmp_path)["passed"]


def test_discovery_requires_boot_bound_file_and_current_declared_listeners(
    tmp_path, monkeypatch
):
    boot_id = "00000000-0000-0000-0000-000000000001"
    write_fixture(tmp_path, "proc/sys/kernel/random/boot_id", boot_id.encode())
    recorded = write_fixture(
        tmp_path,
        f"tmp/sticks_costaricto/service_discovery_{boot_id}.txt",
        b"=== LISTENING TCP SERVICES ===\n"
        b"LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n"
        b"LISTEN 0 128 0.0.0.0:80 0.0.0.0:*\n"
        b"=== LISTENING UDP SERVICES ===\n",
        0o600,
    )
    monkeypatch.setattr(
        probe.pwd,
        "getpwuid",
        lambda user_id: SimpleNamespace(pw_name="reconuser"),
    )
    current = b"LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\nLISTEN 0 128 0.0.0.0:80 0.0.0.0:*\n"
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, current.decode(), ""
        ),
    )
    assert probe.measure_discovery(tmp_path)["passed"]
    recorded.write_text("LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n")
    assert not probe.measure_discovery(tmp_path)["passed"]
    recorded.write_text(
        "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\nLISTEN 0 128 0.0.0.0:80 0.0.0.0:*\n"
    )
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n", ""
        ),
    )
    assert not probe.measure_discovery(tmp_path)["passed"]


def test_discovery_rejects_stale_boot_and_symlink(tmp_path, monkeypatch):
    write_fixture(
        tmp_path,
        "proc/sys/kernel/random/boot_id",
        b"00000000-0000-0000-0000-000000000002",
    )
    with pytest.raises(FileNotFoundError):
        probe.measure_discovery(tmp_path)
    destination = (
        tmp_path
        / "tmp/sticks_costaricto/service_discovery_00000000-0000-0000-0000-000000000002.txt"
    )
    destination.parent.mkdir(parents=True)
    destination.symlink_to(tmp_path / "proc/sys/kernel/random/boot_id")
    with pytest.raises(OSError):
        probe.measure_discovery(tmp_path)
