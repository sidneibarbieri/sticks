"""Observe bounded CostaRicto fixtures and SSH state inside the target guest."""

import hashlib
import json
import os
import pwd
import socket
import stat
import subprocess
from pathlib import Path


COLLECTION_TEXT = b"Quarterly revenue notes for controlled collection testing."
TOOL_TEXT = b"#!/bin/bash\nss -tlnp\n"
PAYLOAD_SHA256 = "b088ddaef2625e7f19f1ef1031b8af0617d4e849134d367bde139c77b7ad7be9"
SCOPE = (
    "Declared synthetic guest files, copies, benign payload, and listening SSH; "
    "not external tool acquisition or complete historical campaign effects."
)


def read_regular(path: Path) -> bytes:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= 65536:
        raise ValueError(f"Missing or invalid guest fixture: {path}")
    return path.read_bytes()


def observe_copy(
    source: Path, destination: Path, expected: bytes, expected_mode: int,
) -> tuple[dict[str, bool], dict[str, str]]:
    source_bytes = read_regular(source)
    destination_bytes = read_regular(destination)
    destination_stat = destination.stat()
    checks = {
        "source_declared": source_bytes.rstrip(b"\n") == expected.rstrip(b"\n"),
        "copy_matches_source": source_bytes == destination_bytes,
        "destination_owner_mode": (
            pwd.getpwuid(destination_stat.st_uid).pw_name == "reconuser"
            and stat.S_IMODE(destination_stat.st_mode) == expected_mode
        ),
    }
    hashes = {
        "source": hashlib.sha256(source_bytes).hexdigest(),
        "destination": hashlib.sha256(destination_bytes).hexdigest(),
    }
    return checks, hashes


def collect_observation(root: Path) -> dict:
    collection_checks, collection_hashes = observe_copy(
        root / "home/reconuser/collection/finance_notes.txt",
        root / "tmp/sticks_costaricto/local_collection.txt", COLLECTION_TEXT, 0o600,
    )
    tool_checks, tool_hashes = observe_copy(
        root / "home/reconuser/tools/network_scan.sh",
        root / "tmp/sticks_costaricto/network_scan.sh", TOOL_TEXT, 0o755,
    )
    payload_hash = hashlib.sha256(read_regular(root / "tmp/sticks_downloaded_payload.sh")).hexdigest()
    listening = subprocess.check_output(["ss", "-H", "-tln"], text=True)
    tcp_ports = {
        int(line.split()[3].rsplit(":", 1)[1]) for line in listening.splitlines()
    }
    checks = {
        "declared_target_hostname": socket.gethostname() == "target-linux-1",
        "declared_ssh_service_listening": 22 in tcp_ports,
        "collection_source_declared": collection_checks["source_declared"],
        "collection_copy_matches_source": collection_checks["copy_matches_source"],
        "collection_destination_owner_mode": collection_checks["destination_owner_mode"],
        "tool_source_declared": tool_checks["source_declared"],
        "tool_copy_matches_source": tool_checks["copy_matches_source"],
        "tool_destination_owner_mode": tool_checks["destination_owner_mode"],
        "known_benign_payload_present": payload_hash == PAYLOAD_SHA256,
    }
    return {
        "schema": "costaricto-bounded-guest-observation/v1",
        "hostname": socket.gethostname(),
        "observer_uid": os.geteuid(),
        "boot_id": (root / "proc/sys/kernel/random/boot_id").read_text().strip(),
        "checks": checks,
        "passed": all(checks.values()),
        "file_sha256": {
            "collection_source": collection_hashes["source"],
            "collection_copy": collection_hashes["destination"],
            "tool_source": tool_hashes["source"],
            "tool_copy": tool_hashes["destination"],
            "benign_payload": payload_hash,
        },
        "scope": SCOPE,
    }


def main() -> int:
    observation = collect_observation(Path("/"))
    print(json.dumps(observation, sort_keys=True))
    return int(not observation["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
