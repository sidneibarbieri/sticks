"""Read-only predicates for CostaRicto's bounded guest file effects."""

import hashlib
import os
from pathlib import Path
import pwd
import stat
import subprocess


PAYLOAD = b"#!/bin/sh\necho STICKS benign payload\n"
COLLECTION = b"Quarterly revenue notes for controlled collection testing."
DECLARED_TCP_PORTS = frozenset({22, 80})


def read_fixture(
    root: Path, relative: str, maximum_bytes: int
) -> tuple[bytes, os.stat_result]:
    """Read one bounded regular file without following directory or file symlinks."""
    components = relative.split("/")
    if not components or any(component in {"", ".", ".."} for component in components):
        raise ValueError("Invalid guest fixture path")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in components[:-1]:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        file_descriptor = os.open(
            components[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=descriptor,
        )
        with os.fdopen(file_descriptor, "rb") as source:
            metadata = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or not 0 < metadata.st_size <= maximum_bytes
            ):
                raise ValueError("Missing or invalid bounded guest fixture")
            content = source.read(maximum_bytes + 1)
    finally:
        os.close(descriptor)
    if not 0 < len(content) <= maximum_bytes:
        raise ValueError("Guest fixture changed beyond its bounded size")
    return content, metadata


def measure_transfer(root: Path) -> dict[str, str | bool]:
    """Check the guest loopback HTTP transfer, not cross-host ingress."""
    source, _ = read_fixture(root, "tmp/sticks_t1105/payload.sh", 4096)
    destination, destination_stat = read_fixture(
        root, "tmp/sticks_downloaded_payload.sh", 4096
    )
    log, _ = read_fixture(root, "tmp/sticks_t1105_server.log", 65536)
    return {
        "passed": source == PAYLOAD
        and destination == source
        and bool(destination_stat.st_mode & stat.S_IXUSR)
        and b'"GET /payload.sh HTTP/1.1" 200' in log,
        "content_sha256": hashlib.sha256(destination).hexdigest(),
        "input_sha256": hashlib.sha256(source).hexdigest(),
    }


def measure_collection(root: Path) -> dict[str, str | bool]:
    """Check the declared local source and occurrence-produced guest copy."""
    source, _ = read_fixture(root, "home/reconuser/collection/finance_notes.txt", 65536)
    destination, destination_stat = read_fixture(
        root, "tmp/sticks_costaricto/local_collection.txt", 65536
    )
    return {
        "passed": source.rstrip(b"\n") == COLLECTION
        and destination == source
        and stat.S_IMODE(destination_stat.st_mode) == 0o600
        and pwd.getpwuid(destination_stat.st_uid).pw_name == "reconuser",
        "content_sha256": hashlib.sha256(destination).hexdigest(),
        "input_sha256": hashlib.sha256(source).hexdigest(),
    }


def listening_ports(content: str) -> frozenset[int]:
    """Extract TCP listener ports from one bounded ss output."""
    ports = set()
    for line in content.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[0] != "LISTEN":
            continue
        address = fields[3]
        if ":" not in address:
            continue
        port = address.rsplit(":", 1)[1]
        if port.isdecimal():
            ports.add(int(port))
    return frozenset(ports)


def measure_discovery(root: Path) -> dict[str, str | bool]:
    """Check a boot-bound guest listing against independently queried listeners."""
    boot_id = (root / "proc/sys/kernel/random/boot_id").read_text().strip()
    if not boot_id or "/" in boot_id or ".." in boot_id:
        raise ValueError("Invalid guest boot identity")
    content, metadata = read_fixture(
        root, f"tmp/sticks_costaricto/service_discovery_{boot_id}.txt", 65536
    )
    live = subprocess.run(
        ["ss", "-H", "-tln"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    recorded_tcp = content.decode("utf-8").split("=== LISTENING UDP SERVICES ===", 1)[0]
    content_digest = hashlib.sha256(content).hexdigest()
    return {
        "passed": stat.S_IMODE(metadata.st_mode) == 0o600
        and pwd.getpwuid(metadata.st_uid).pw_name == "reconuser"
        and DECLARED_TCP_PORTS <= listening_ports(recorded_tcp)
        and DECLARED_TCP_PORTS <= listening_ports(live),
        "content_sha256": content_digest,
        "input_sha256": content_digest,
    }
