"""The guest sampler binds procfs counters to boot, owner and command."""

import hashlib
import os
import pwd
import socket
from pathlib import Path

import pytest

from runners.capability_facts import FactScope
from runners.target_compute_predicate import evaluate_target_cpu_delta
from runners.target_process_cpu_sampler import collect_target_process_cpu_sample


def process_stat(process_id: int, user_ticks: int, start_ticks: int) -> bytes:
    fields = [b"0"] * 20
    fields[0] = b"S"
    fields[11] = str(user_ticks).encode()
    fields[12] = b"2"
    fields[19] = str(start_ticks).encode()
    return f"{process_id} (cpu worker) ".encode() + b" ".join(fields) + b"\n"


@pytest.fixture
def guest_proc(tmp_path: Path) -> tuple[Path, FactScope, str]:
    boot_path = tmp_path / "sys/kernel/random/boot_id"
    boot_path.parent.mkdir(parents=True)
    boot_path.write_text("boot-1\n")
    process_dir = tmp_path / "123"
    process_dir.mkdir()
    (process_dir / "stat").write_bytes(process_stat(123, 20, 400))
    command = b"python3\0-c\0bounded-workload\0run-nonce-1\0"
    (process_dir / "cmdline").write_bytes(command)
    scope = FactScope(
        run_id="run-1",
        environment_id="environment-1",
        epoch="boot-1",
        locus="target",
        host_id=socket.gethostname(),
        principal=pwd.getpwuid(os.getuid()).pw_name,
    )
    return tmp_path, scope, hashlib.sha256(command).hexdigest()


def collect(guest_proc: tuple[Path, FactScope, str]):
    proc_root, scope, command_sha256 = guest_proc
    return collect_target_process_cpu_sample(
        scope,
        123,
        expected_nonce="run-nonce-1",
        expected_command_sha256=command_sha256,
        proc_root=proc_root,
    )


def test_collected_cpu_progress_passes_only_after_counter_change(guest_proc) -> None:
    proc_root, _, _ = guest_proc
    before = collect(guest_proc)
    (proc_root / "123/stat").write_bytes(process_stat(123, 35, 400))
    after = collect(guest_proc)

    verdict = evaluate_target_cpu_delta(before, after, minimum_cpu_ticks=10)
    assert verdict.passed
    assert verdict.cpu_ticks_delta == 15


def test_idle_process_is_a_negative_control(guest_proc) -> None:
    before = collect(guest_proc)
    after = collect(guest_proc)
    assert not evaluate_target_cpu_delta(before, after, minimum_cpu_ticks=1).passed


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ("boot", "boot"),
        ("command", "command"),
        ("owner", "owner"),
        ("nonce", "nonce"),
        ("process", "stat identity"),
    ),
)
def test_untrusted_or_drifted_process_is_rejected(guest_proc, change, message) -> None:
    proc_root, scope, command_sha256 = guest_proc
    if change == "boot":
        (proc_root / "sys/kernel/random/boot_id").write_text("boot-2\n")
    elif change == "command":
        (proc_root / "123/cmdline").write_bytes(b"python3\0run-nonce-1\0")
    elif change == "owner":
        scope = scope.model_copy(update={"principal": "not-the-owner"})
    elif change == "nonce":
        (proc_root / "123/cmdline").write_bytes(b"python3\0wrong-nonce\0")
    else:
        (proc_root / "123/stat").write_bytes(process_stat(124, 20, 400))

    with pytest.raises(ValueError, match=message):
        collect_target_process_cpu_sample(
            scope,
            123,
            expected_nonce="run-nonce-1",
            expected_command_sha256=command_sha256,
            proc_root=proc_root,
        )


def test_symlinked_process_directory_is_rejected(guest_proc) -> None:
    proc_root, scope, command_sha256 = guest_proc
    (proc_root / "123").rename(proc_root / "actual")
    (proc_root / "123").symlink_to(proc_root / "actual", target_is_directory=True)
    with pytest.raises(ValueError, match="real guest process directory"):
        collect_target_process_cpu_sample(
            scope,
            123,
            expected_nonce="run-nonce-1",
            expected_command_sha256=command_sha256,
            proc_root=proc_root,
        )
