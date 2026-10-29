"""Observe retained ShadowRay guest fixtures without executing the technique."""

import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
from contextlib import ExitStack
from types import MappingProxyType

MAX_FIXTURE_BYTES = 262144
TRANSFER_PAYLOAD = b'#!/bin/bash\necho "Network Reconnaissance Tool"\necho "Target: ${1:-127.0.0.1}"\necho "Mode: ${2:-ping}"\n'
TOOLKIT_SHA256 = MappingProxyType(
    {
        "port_scanner.py": "83a2ca4b1764db5f4456b5f5fc017be6967e1af0b256a57ca014e3d68d884c0c",
        "service_enum.sh": "82debdb73005a09027938daa32a4ffb01daf21b2190160c5f1f8927ac71365bf",
        "sys_profiler.py": "2259202e3c6dd7864d660be26dc9696135e54ac8962f134f2758a9c5663746c7",
    }
)


FILE_PATHS = (
    "sticks-shadowray-transfer/source/network_tool.sh",
    "sticks-shadowray-transfer/downloaded_tool.sh",
    "sticks-shadowray-persistence/.bashrc_sticks_simulation",
    "sticks-shadowray-persistence/.bashrc_sticks_backup",
    "sticks-shadowray-toolkit/port_scanner.py",
    "sticks-shadowray-toolkit/service_enum.sh",
    "sticks-shadowray-toolkit/sys_profiler.py",
)


def read_regular(path: Path) -> tuple[bytes, os.stat_result]:
    """Read bounded bytes without following file or ancestor symlinks."""
    absolute = path.absolute()
    with ExitStack() as opened:
        directory = os.open(
            absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        opened.callback(os.close, directory)
        for component in absolute.parts[1:-1]:
            directory = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory,
            )
            opened.callback(os.close, directory)
        initial = os.stat(absolute.name, dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(initial.st_mode):
            raise ValueError("Expected a regular fixture file")
        descriptor = os.open(
            absolute.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        opened.callback(os.close, descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or not 0 < metadata.st_size <= MAX_FIXTURE_BYTES
        ):
            raise ValueError("Fixture size outside observation boundary")
        content = os.read(descriptor, MAX_FIXTURE_BYTES + 1)
        final = os.fstat(descriptor)
        if len(content) != metadata.st_size or (
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        ) != (final.st_size, final.st_mtime_ns, final.st_ctime_ns):
            raise ValueError("Guest fixture changed during bounded observation")
    return content, metadata


def file_metadata(content: bytes, metadata: os.stat_result) -> dict:
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": metadata.st_size,
        "owner": pwd.getpwuid(metadata.st_uid).pw_name,
        "mode": format(stat.S_IMODE(metadata.st_mode), "o"),
        "executable": bool(metadata.st_mode & stat.S_IXUSR),
    }


def observe_file(path: Path) -> dict:
    return file_metadata(*read_regular(path))


def measure_transfer(root: Path) -> dict:
    source, _ = read_regular(root / "sticks-shadowray-transfer/source/network_tool.sh")
    target, metadata = read_regular(
        root / "sticks-shadowray-transfer/downloaded_tool.sh"
    )
    log, _ = read_regular(root / "sticks-shadowray-http.log")
    return {
        "passed": source == target == TRANSFER_PAYLOAD
        and bool(metadata.st_mode & stat.S_IXUSR)
        and b'"GET /network_tool.sh HTTP/1.1" 200' in log,
        "content_sha256": hashlib.sha256(target).hexdigest(),
        "input_sha256": hashlib.sha256(source).hexdigest(),
        "target_executable": bool(metadata.st_mode & stat.S_IXUSR),
        "http_get_recorded": b'"GET /network_tool.sh HTTP/1.1" 200' in log,
        "owner": pwd.getpwuid(metadata.st_uid).pw_name,
    }


def measure_toolkit(root: Path) -> dict:
    files = {
        name: observe_file(root / "sticks-shadowray-toolkit" / name)
        for name in TOOLKIT_SHA256
    }
    return {
        "passed": all(
            files[name]["sha256"] == expected and files[name]["executable"]
            for name, expected in TOOLKIT_SHA256.items()
        ),
        "files": files,
    }


def collect_fixture_observation(predicate_id: str, nonce: str) -> dict:
    """Observe one declared fixture set without executing its producer."""
    if predicate_id == "toolkit-staged":
        measurement = measure_toolkit(Path("/tmp"))
        measurement["files"] = tuple(
            {"name": name, **metadata}
            for name, metadata in measurement["files"].items()
        )
    elif predicate_id == "loopback-transfer":
        measurement = measure_transfer(Path("/tmp"))
    else:
        raise ValueError("Unknown C0045 fixture predicate")
    return {
        "hostname": socket.gethostname(),
        "principal": pwd.getpwuid(os.geteuid()).pw_name,
        "observer_uid": os.geteuid(),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "nonce": nonce,
        "measurement": measurement,
    }


def execution_trace_path(nonce: str) -> Path:
    if re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
        raise ValueError("Invalid trace acquisition nonce")
    return Path("/tmp/sticks-c0045-exec-" + nonce + ".trace")


def collect_execution_trace(nonce: str) -> dict:
    content, metadata = read_regular(execution_trace_path(nonce))
    return {
        "hostname": socket.gethostname(),
        "principal": pwd.getpwuid(os.geteuid()).pw_name,
        "observer_uid": os.geteuid(),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "nonce": nonce,
        "owner": pwd.getpwuid(metadata.st_uid).pw_name,
        "trace": content.decode("utf-8"),
        "trace_sha256": hashlib.sha256(content).hexdigest(),
    }


def collect_observation(
    root: Path, boot_id_path: Path = Path("/proc/sys/kernel/random/boot_id")
) -> dict:
    files = {relative: observe_file(root / relative) for relative in FILE_PATHS}
    http_log = root / "sticks-shadowray-http.log"
    http_log_content, http_log_stat = read_regular(http_log)
    http_log_metadata = file_metadata(http_log_content, http_log_stat)
    checks = {
        "transfer_matches_source": files[FILE_PATHS[0]]["sha256"]
        == files[FILE_PATHS[1]]["sha256"],
        "http_get_recorded": '"GET /network_tool.sh HTTP/1.1" 200'
        in http_log_content.decode("utf-8"),
        "backup_matches_fixture": files[FILE_PATHS[2]]["sha256"]
        == files[FILE_PATHS[3]]["sha256"],
        "toolkit_files_executable": all(
            files[relative]["executable"] for relative in FILE_PATHS[4:]
        ),
    }
    return {
        "schema": "shadowray-fixture-observation/v1",
        "hostname": socket.gethostname(),
        "observer_uid": os.geteuid(),
        "boot_id": boot_id_path.read_text().strip(),
        "files": files,
        "http_log": http_log_metadata,
        "checks": checks,
        "passed": all(checks.values()),
        "scope": "Retained fixtures only; no proof of escalation, historical fidelity, "
        "executor identity, shell-startup behavior, or cross-host ingress.",
    }


def main() -> int:
    observation = collect_observation(Path("/tmp"))
    print(json.dumps(observation, sort_keys=True))
    return 0 if observation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
