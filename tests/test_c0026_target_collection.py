"""C0026 collection must bind to the prepared target, not the host."""

import subprocess

import pytest

from executors import legacy_parity_expansion_executors as collection


def test_c0026_collects_declared_files_in_target_vm(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, int, str]] = []

    def run_target(
        sut_profile_id: str, bash_script: str, timeout: int, execution_user: str
    ) -> subprocess.CompletedProcess[str]:
        calls.append((sut_profile_id, bash_script, timeout, execution_user))
        return subprocess.CompletedProcess(["vagrant", "ssh"], 0, "digest  collection\n", "")

    monkeypatch.setattr(collection, "run_bash_on_target_vm", run_target)
    monkeypatch.setattr(
        collection,
        "_seed_collection_files",
        lambda campaign_id: pytest.fail("C0026 must not collect on the host"),
    )

    success, stdout, stderr, artifacts = collection.execute_t1005_real(
        "0.c0026", "0.c0026"
    )

    assert success
    assert "target VM" in stdout
    assert stderr == ""
    assert artifacts == ["target-vm:/tmp/sticks_t1005/local_collection.txt"]
    assert calls[0][0] == "0.c0026"
    assert "andromeda_notes.txt" in calls[0][1]
    assert "report_2021.txt" in calls[0][1]
    assert calls[0][2] == 60
    assert calls[0][3] == "ubuntu"


def test_c0026_target_failure_does_not_fall_back_to_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        collection,
        "run_bash_on_target_vm",
        lambda **kwargs: subprocess.CompletedProcess(["vagrant", "ssh"], 1, "", "guest failed"),
    )
    monkeypatch.setattr(
        collection,
        "_seed_collection_files",
        lambda campaign_id: pytest.fail("C0026 must not fall back to the host"),
    )

    with pytest.raises(subprocess.CalledProcessError):
        collection.execute_t1005_real("0.c0026", "0.c0026")
