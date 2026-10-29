"""CostaRicto collection and tool staging must use declared guest fixtures."""

import subprocess
import stat
import os
import platform
import shutil

import pytest

from executors import legacy_parity_expansion_executors as executors
from executors.executor_registry import ExecutionMode, registry
from executors.registry_initializer import initialize_registry


def test_staging_a_tool_does_not_assert_new_code_execution():
    initialize_registry(force=True)
    metadata = registry.get_metadata("T1588.002", "0.costaricto")
    assert metadata.execution_mode is ExecutionMode.NAIVE_SIMULATED
    assert "code_execution" not in metadata.produces
    assert metadata.produces == ["simulation:guest_tool_staged"]


def test_copying_a_known_guest_fixture_does_not_assert_file_discovery():
    initialize_registry(force=True)
    metadata = registry.get_metadata("T1005", "0.costaricto")
    assert metadata.execution_mode is ExecutionMode.REAL_CONTROLLED
    assert metadata.produces == ["collection:local_data"]
    assert metadata.requires == []


@pytest.mark.parametrize("technique,source,destination,mode", [
    ("T1005", "/home/reconuser/collection/finance_notes.txt", "/tmp/sticks_costaricto/local_collection.txt", "600"),
    ("T1588.002", "/home/reconuser/tools/network_scan.sh", "/tmp/sticks_costaricto/network_scan.sh", "755"),
])
def test_costaricto_files_are_staged_on_the_target(monkeypatch, tmp_path, technique, source, destination, mode):
    initialize_registry(force=True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    calls = []

    def target_transport(**arguments):
        calls.append(arguments)
        return subprocess.CompletedProcess([], 0, "declared-source-hash\n", "")

    monkeypatch.setattr(executors, "run_bash_on_target_vm", target_transport)
    result = registry.get_executor(technique, "0.costaricto")("0.costaricto", "0.costaricto")
    assert calls and calls[0]["sut_profile_id"] == "0.costaricto"
    assert calls[0]["execution_user"] == "reconuser"
    assert source in calls[0]["bash_script"] and destination in calls[0]["bash_script"]
    assert "65536" in calls[0]["bash_script"]
    assert "install -m " + mode in calls[0]["bash_script"]
    assert result[0] is True and result[2] == ""
    assert result[3] == ["target-vm:" + destination]
    assert list((tmp_path / "data/artifacts").iterdir()) == []


@pytest.mark.parametrize("technique", ["T1005", "T1588.002"])
def test_costaricto_guest_failure_cannot_become_local_success(monkeypatch, tmp_path, technique):
    initialize_registry(force=True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    monkeypatch.setattr(executors, "run_bash_on_target_vm", lambda **arguments:
                        subprocess.CompletedProcess(["guest-stage"], 9, "", "fixture missing"))
    with pytest.raises(subprocess.CalledProcessError) as failure:
        registry.get_executor(technique, "0.costaricto")("0.costaricto", "0.costaricto")
    assert failure.value.returncode == 9
    assert failure.value.stderr == "fixture missing"
    assert list((tmp_path / "data/artifacts").iterdir()) == []


@pytest.mark.parametrize("technique,source_name,destination_name,mode", [
    ("T1005", "collection/finance_notes.txt", "local_collection.txt", 0o600),
    ("T1588.002", "tools/network_scan.sh", "network_scan.sh", 0o755),
])
@pytest.mark.parametrize("source_kind", ["regular", "symlink", "oversized"])
def test_emitted_shell_copies_only_bounded_regular_fixtures(
    monkeypatch, tmp_path, technique, source_name, destination_name, mode, source_kind,
):
    initialize_registry(force=True)
    source = tmp_path / "home/reconuser" / source_name
    source.parent.mkdir(parents=True)
    content = b"declared fixture\n" if source_kind != "oversized" else b"x" * 65537
    if source_kind == "symlink":
        original = tmp_path / "original"
        original.write_bytes(content)
        source.symlink_to(original)
    else:
        source.write_bytes(content)
    destination = tmp_path / "staging" / destination_name
    environment = os.environ.copy()
    if platform.system() == "Darwin":
        utilities = {"stat": shutil.which("gstat"), "install": shutil.which("ginstall")}
        if not all(utilities.values()):
            pytest.skip("Guest-shell test requires GNU stat and install on macOS")
        tool_directory = tmp_path / "gnu-tools"
        tool_directory.mkdir()
        for name, executable in utilities.items():
            (tool_directory / name).symlink_to(executable)
        environment["PATH"] = str(tool_directory) + os.pathsep + environment["PATH"]

    def local_shell_for_transport(**arguments):
        script = arguments["bash_script"].replace("/home/reconuser", str(tmp_path / "home/reconuser"))
        script = script.replace("/tmp/sticks_costaricto", str(tmp_path / "staging"))
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=environment)

    monkeypatch.setattr(executors, "run_bash_on_target_vm", local_shell_for_transport)
    executor = registry.get_executor(technique, "0.costaricto")
    if source_kind == "regular":
        result = executor("0.costaricto", "0.costaricto")
        assert result[0] is True
        assert destination.read_bytes() == content
        assert stat.S_IMODE(destination.stat().st_mode) == mode
    else:
        with pytest.raises(subprocess.CalledProcessError):
            executor("0.costaricto", "0.costaricto")
        assert not destination.exists()
