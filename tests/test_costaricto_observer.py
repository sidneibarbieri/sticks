"""CostaRicto observations bind bounded guest state, not historical effects."""

import json
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import observe_costaricto_target as observer
from scripts import probe_costaricto_target as probe
from scripts.run_isolated_lab_campaign import write_json


def make_guest(tmp_path: Path, monkeypatch) -> Path:
    def create_file(relative: str, content: bytes, mode: int) -> None:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)

    create_file("home/reconuser/collection/finance_notes.txt", probe.COLLECTION_TEXT, 0o600)
    create_file("tmp/sticks_costaricto/local_collection.txt", probe.COLLECTION_TEXT, 0o600)
    create_file("home/reconuser/tools/network_scan.sh", probe.TOOL_TEXT, 0o755)
    create_file("tmp/sticks_costaricto/network_scan.sh", probe.TOOL_TEXT, 0o755)
    create_file("tmp/sticks_downloaded_payload.sh", b"#!/bin/sh\necho STICKS benign payload\n", 0o755)
    create_file("proc/sys/kernel/random/boot_id", b"synthetic-boot\n", 0o644)
    monkeypatch.setattr(probe.socket, "gethostname", lambda: "target-linux-1")
    monkeypatch.setattr(probe.os, "geteuid", lambda: 0)
    monkeypatch.setattr(probe.pwd, "getpwuid", lambda _: SimpleNamespace(pw_name="reconuser"))
    monkeypatch.setattr(probe.subprocess, "check_output", lambda *args, **kwargs: "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n")
    return tmp_path


def test_probe_accepts_only_bounded_guest_fixtures(tmp_path, monkeypatch):
    guest = make_guest(tmp_path, monkeypatch)

    observation = probe.collect_observation(guest)

    assert observation["passed"] is True
    assert set(observation["checks"]) == {
        "declared_target_hostname", "declared_ssh_service_listening",
        "collection_source_declared", "collection_copy_matches_source",
        "collection_destination_owner_mode", "tool_source_declared",
        "tool_copy_matches_source", "tool_destination_owner_mode",
        "known_benign_payload_present",
    }
    assert all(observation["checks"].values())
    assert "not external tool acquisition" in observation["scope"]


def test_probe_rejects_changed_copy(tmp_path, monkeypatch):
    guest = make_guest(tmp_path, monkeypatch)
    (guest / "tmp/sticks_costaricto/local_collection.txt").write_text("other data")

    observation = probe.collect_observation(guest)

    assert observation["passed"] is False
    assert observation["checks"]["collection_copy_matches_source"] is False


def test_probe_rejects_symlink_destination(tmp_path, monkeypatch):
    guest = make_guest(tmp_path, monkeypatch)
    destination = guest / "tmp/sticks_costaricto/network_scan.sh"
    destination.unlink()
    destination.symlink_to(guest / "home/reconuser/tools/network_scan.sh")

    with pytest.raises(ValueError, match="invalid guest fixture"):
        probe.collect_observation(guest)


def test_observer_persists_raw_failure_without_success_receipt(tmp_path, monkeypatch):
    run_root = tmp_path / "run"
    probe_path = run_root / "workspace/scripts/probe_costaricto_target.py"
    probe_path.parent.mkdir(parents=True)
    probe_path.write_text("print('probe')\n")
    (run_root / "workspace/lab/vagrant/target-linux-1").mkdir(parents=True)
    (run_root / "evidence").mkdir()
    write_json(run_root / "run_context.json", {
        "campaign_id": "0.costaricto", "exit_code": 0,
        "keep_lab_requested": True, "source_tree_sha256": "source-digest",
    })
    monkeypatch.setattr(observer.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess([], 7, "", "guest probe failed"))
    monkeypatch.setattr("sys.argv", ["observe_costaricto_target", "--run-root", str(run_root)])

    with pytest.raises(RuntimeError, match="Target observation failed"):
        observer.main()

    transport = json.loads((run_root / "evidence/costaricto-target-observation.transport.json").read_text())
    assert transport["exit_code"] == 7
    assert transport["stderr"] == "guest probe failed"
    assert not (run_root / "evidence/costaricto-target-observation.json").exists()


def test_guest_fixture_mode_is_checked(tmp_path, monkeypatch):
    guest = make_guest(tmp_path, monkeypatch)
    destination = guest / "tmp/sticks_costaricto/local_collection.txt"
    destination.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)

    observation = probe.collect_observation(guest)

    assert observation["passed"] is False
    assert observation["checks"]["collection_destination_owner_mode"] is False
