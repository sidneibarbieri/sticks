"""C0045 treatment command identity is fixed before any guest launch."""

import hashlib
import subprocess

import pytest

from executors.c0045_compute_command import (
    WORKLOAD_CODE,
    build_c0045_compute_command,
)


def test_command_hash_covers_frozen_argv_and_nonce() -> None:
    nonce = "prospectivecontrol001"

    selection = build_c0045_compute_command(nonce)

    argv = ("python3", "-c", WORKLOAD_CODE, nonce, "15")
    expected_bytes = b"\0".join(argument.encode() for argument in argv) + b"\0"
    assert selection.expected_command_sha256 == hashlib.sha256(expected_bytes).hexdigest()
    assert selection.duration_seconds == 15
    assert nonce in selection.launch_script


def test_workload_source_is_valid_python_without_running_a_control() -> None:
    completed = subprocess.run(
        ["python3", "-c", WORKLOAD_CODE, "validationnonce001", "0"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert completed.returncode == 0
    assert completed.stdout == ""


@pytest.mark.parametrize("nonce", ("short", "bad space nonce 123", "x" * 129))
def test_nonce_outside_literal_bound_is_rejected(nonce: str) -> None:
    with pytest.raises(ValueError, match="bounded literal"):
        build_c0045_compute_command(nonce)


def test_changed_workload_code_requires_a_new_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("executors.c0045_compute_command.WORKLOAD_CODE", "print('changed')")

    with pytest.raises(ValueError, match="workload source differs"):
        build_c0045_compute_command("prospectivecontrol001")
