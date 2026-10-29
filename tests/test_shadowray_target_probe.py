"""Guest observation rejects missing, changed, or non-regular fixtures."""

import importlib.util
from pathlib import Path

import pytest
import subprocess
from executors import shadowray_fixed_executors


PROBE_PATH = Path(__file__).resolve().parents[1] / "scripts/probe_shadowray_target.py"
SPEC = importlib.util.spec_from_file_location("shadowray_probe", PROBE_PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


@pytest.fixture
def fixtures(tmp_path):
    for relative in probe.FILE_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("benign fixture\n")
        path.chmod(0o755)
    (tmp_path / "sticks-shadowray-http.log").write_text(
        '127.0.0.1 "GET /network_tool.sh HTTP/1.1" 200 -\n'
    )
    boot_id = tmp_path / "boot-id"
    boot_id.write_text("controlled-test-boot\n")
    return tmp_path, boot_id


def test_declared_fixture_checks_pass(fixtures):
    observation = probe.collect_observation(*fixtures)
    assert observation["passed"]
    assert all(observation["checks"].values())
    assert observation["boot_id"] == "controlled-test-boot"
    assert "no proof of escalation" in observation["scope"]


@pytest.mark.parametrize("relative", [probe.FILE_PATHS[1], probe.FILE_PATHS[3]])
def test_changed_file_rejects_observation(fixtures, relative):
    root, boot_id = fixtures
    (root / relative).write_text("changed fixture\n")
    assert not probe.collect_observation(root, boot_id)["passed"]


def test_missing_fixture_is_visible(fixtures):
    root, boot_id = fixtures
    (root / probe.FILE_PATHS[1]).unlink()
    with pytest.raises(FileNotFoundError):
        probe.collect_observation(root, boot_id)


@pytest.mark.parametrize("size", [0, probe.MAX_FIXTURE_BYTES + 1])
def test_fixture_size_is_bounded(tmp_path, size):
    fixture = tmp_path / "fixture"
    fixture.write_bytes(b"x" * size)
    with pytest.raises(ValueError, match="size outside"):
        probe.read_regular(fixture)


def test_fifo_is_rejected_before_open(tmp_path):
    fixture = tmp_path / "fixture"
    probe.os.mkfifo(fixture)
    with pytest.raises(ValueError, match="regular fixture"):
        probe.read_regular(fixture)


def test_mutation_during_read_is_rejected(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture"
    fixture.write_bytes(b"before")
    original_read = probe.os.read

    def mutate_after_read(descriptor, size):
        content = original_read(descriptor, size)
        fixture.write_bytes(b"after and longer")
        return content

    monkeypatch.setattr(probe.os, "read", mutate_after_read)
    with pytest.raises(ValueError, match="changed during"):
        probe.read_regular(fixture)


def test_symlink_is_rejected(fixtures):
    root, boot_id = fixtures
    downloaded = root / probe.FILE_PATHS[1]
    downloaded.unlink()
    downloaded.symlink_to(root / probe.FILE_PATHS[0])
    with pytest.raises(ValueError, match="regular fixture"):
        probe.collect_observation(root, boot_id)


def test_missing_http_request_is_rejected(fixtures):
    root, boot_id = fixtures
    (root / "sticks-shadowray-http.log").write_text("server started\n")
    observation = probe.collect_observation(root, boot_id)
    assert not observation["checks"]["http_get_recorded"]
    assert not observation["passed"]


def test_non_executable_tool_is_rejected(fixtures):
    root, boot_id = fixtures
    (root / probe.FILE_PATHS[4]).chmod(0o644)
    observation = probe.collect_observation(root, boot_id)
    assert not observation["checks"]["toolkit_files_executable"]
    assert not observation["passed"]


def test_symlinked_fixture_directory_is_rejected(fixtures):
    root, boot_id = fixtures
    directory = root / "sticks-shadowray-transfer"
    moved = root / "other-transfer"
    directory.rename(moved)
    directory.symlink_to(moved, target_is_directory=True)
    with pytest.raises(OSError):
        probe.collect_observation(root, boot_id)


def test_transfer_predicate_needs_no_later_campaign_files(tmp_path):
    payload = b'#!/bin/bash\necho "Network Reconnaissance Tool"\necho "Target: ${1:-127.0.0.1}"\necho "Mode: ${2:-ping}"\n'
    source = tmp_path / "sticks-shadowray-transfer/source/network_tool.sh"
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)
    target = tmp_path / "sticks-shadowray-transfer/downloaded_tool.sh"
    target.write_bytes(payload)
    target.chmod(0o755)
    (tmp_path / "sticks-shadowray-http.log").write_text(
        '"GET /network_tool.sh HTTP/1.1" 200\n'
    )
    assert probe.measure_transfer(tmp_path)["passed"]
    source.write_bytes(b"changed together\n")
    target.write_bytes(b"changed together\n")
    assert not probe.measure_transfer(tmp_path)["passed"]


def test_toolkit_predicate_accepts_real_staging_and_rejects_tamper(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    toolkit = tmp_path / "sticks-shadowray-toolkit"

    def transport(**kwargs):
        assert kwargs["execution_user"] == "rayuser"
        script = kwargs["bash_script"].replace(
            "/tmp/sticks-shadowray-toolkit", str(toolkit)
        )
        # This case checks staged bytes, not Linux-only profiler execution on macOS.
        script = script.replace('python3 "$toolkit/sys_profiler.py"', "true")
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    monkeypatch.setattr(shadowray_fixed_executors, "run_bash_on_target_vm", transport)
    succeeded, _, _, _ = shadowray_fixed_executors.execute_t1588_002_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )
    assert succeeded
    assert probe.measure_toolkit(tmp_path)["passed"]
    (toolkit / "port_scanner.py").write_text('print("different tool")\n')
    assert not probe.measure_toolkit(tmp_path)["passed"]
