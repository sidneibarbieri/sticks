"""Read one selected Linux process from procfs; emit no command-line bytes."""

import hashlib
import pwd
import socket
import stat
import time
from pathlib import Path


def _parse_process_stat(data: bytes, expected_process_id: int) -> tuple[int, int, int]:
    header, separator, tail = data.rpartition(b") ")
    if not separator or len(tail.split()) < 20:
        raise ValueError("Malformed guest process stat record")
    process_id, command_separator, _ = header.partition(b" (")
    if not command_separator or int(process_id) != expected_process_id:
        raise ValueError("Guest process stat identity mismatch")
    fields = tail.split()
    return int(fields[11]), int(fields[12]), int(fields[19])


def collect_procfs_counters(
    process_id: int,
    *,
    expected_nonce: str,
    expected_command_sha256: str,
    expected_boot_id: str,
    expected_host_id: str,
    expected_principal: str,
    proc_root: Path = Path("/proc"),
) -> dict[str, int | str]:
    """Bind one procfs sample to the preselected command, owner, host and boot."""
    if process_id <= 0 or not expected_nonce or "\0" in expected_nonce:
        raise ValueError("CPU process selection requires a PID and literal nonce")
    boot_id = (proc_root / "sys/kernel/random/boot_id").read_text().strip()
    if expected_boot_id != boot_id:
        raise ValueError("Guest boot does not match the declared run scope")
    hostname = socket.gethostname()
    if expected_host_id != hostname:
        raise ValueError("Guest hostname does not match the declared run scope")

    process_dir = proc_root / str(process_id)
    metadata = process_dir.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("Expected a real guest process directory")
    principal = pwd.getpwuid(metadata.st_uid).pw_name
    if expected_principal != principal:
        raise ValueError("Guest process owner does not match the declared scope")

    stat_before = _parse_process_stat((process_dir / "stat").read_bytes(), process_id)
    command = (process_dir / "cmdline").read_bytes()
    stat_after = _parse_process_stat((process_dir / "stat").read_bytes(), process_id)
    if stat_before[2] != stat_after[2]:
        raise ValueError("Guest process was replaced during observation")
    if not command.endswith(b"\0") or expected_nonce.encode() not in command.split(b"\0"):
        raise ValueError("Guest process command lacks the selected run nonce")
    command_sha256 = hashlib.sha256(command).hexdigest()
    if command_sha256 != expected_command_sha256:
        raise ValueError("Guest process command differs from the frozen selection")

    return {
        "nonce": expected_nonce,
        "process_id": process_id,
        "process_start_ticks": stat_after[2],
        "process_command_sha256": command_sha256,
        "monotonic_ns": time.monotonic_ns(),
        "user_cpu_ticks": stat_after[0],
        "system_cpu_ticks": stat_after[1],
        "boot_id": boot_id,
        "hostname": hostname,
        "principal": principal,
    }
