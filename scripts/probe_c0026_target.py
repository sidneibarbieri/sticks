"""Observe the bounded C0026 collection chain from inside its target VM."""

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import socket
import stat
import tarfile
import subprocess
from contextlib import contextmanager


@contextmanager
def fixture_directory(root: Path, relative: str):
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in relative.split("/") if relative else ():
            if component in {"", ".", ".."}:
                raise ValueError("Invalid fixture directory component")
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def read_fixture(root: Path, relative: str, maximum_bytes: int) -> bytes:
    directory, name = relative.rsplit("/", 1)
    with fixture_directory(root, directory) as parent:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        with os.fdopen(descriptor, "rb") as source:
            metadata = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size > maximum_bytes
            ):
                raise ValueError("Missing or invalid bounded guest fixture")
            content = source.read(maximum_bytes + 1)
    if not 0 < len(content) <= maximum_bytes:
        raise ValueError("Guest fixture changed beyond its bounded size")
    return content


def measure_collection(root: Path) -> dict:
    notes = read_fixture(root, "home/ubuntu/andromeda_notes.txt", 65536)
    report = read_fixture(root, "home/ubuntu/staged_docs/report_2021.txt", 65536)
    collection = read_fixture(root, "tmp/sticks_t1005/local_collection.txt", 131072)
    expected = b"andromeda_notes.txt\n" + notes + b"\nreport_2021.txt\n" + report
    return {
        "passed": collection == expected,
        "content_sha256": hashlib.sha256(collection).hexdigest(),
    }


def observe_collection(root: Path) -> bool:
    return measure_collection(root)["passed"]


def measure_archive(root: Path) -> dict:
    collection = read_fixture(root, "tmp/sticks_t1005/local_collection.txt", 131072)
    archive = read_fixture(root, "tmp/sticks_collected_data.tar.gz", 1048576)
    measurement = {
        "passed": False,
        "content_sha256": hashlib.sha256(archive).hexdigest(),
        "input_sha256": hashlib.sha256(collection).hexdigest(),
    }
    collection_member_seen = False
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r|gz") as package:
        for index, member in enumerate(package):
            if index >= 32 or member.size > 131072:
                raise ValueError("Archive exceeds the bounded member contract")
            if PurePosixPath(member.name).as_posix() != "local_collection.txt":
                continue
            if collection_member_seen:
                raise ValueError("Duplicate collection archive member")
            collection_member_seen = True
            if not member.isfile():
                raise ValueError("Collection archive member must be a regular file")
            extracted = package.extractfile(member)
            if extracted is None:
                raise ValueError("Collection archive member cannot be read")
            measurement["passed"] = extracted.read(131073) == collection
    return measurement


def observe_archive(root: Path) -> bool:
    return measure_archive(root)["passed"]


def chunk_names(root: Path) -> tuple[str, ...]:
    with fixture_directory(root, "tmp") as directory:
        names = tuple(
            sorted(
                name
                for name in os.listdir(directory)
                if name.startswith("sticks_chunk.")
            )
        )
    if len(names) > 8192:
        raise ValueError("Fragment population exceeds the bounded archive size")
    return names


def measure_chunks(root: Path) -> dict:
    archive = read_fixture(root, "tmp/sticks_collected_data.tar.gz", 1048576)
    names = chunk_names(root)
    chunks = [read_fixture(root, f"tmp/{name}", 128) for name in names]
    joined = b"".join(chunks)
    return {
        "passed": len(chunks) >= 2 and joined == archive,
        "content_sha256": hashlib.sha256(joined).hexdigest(),
        "input_sha256": hashlib.sha256(archive).hexdigest(),
    }


def observe_chunks(root: Path) -> bool:
    return measure_chunks(root)["passed"]


def measure_payload(root: Path) -> dict:
    payload = read_fixture(root, "tmp/sticks_downloaded_payload.sh", 4096)
    return {
        "passed": payload == b"#!/bin/sh\necho STICKS benign payload\n",
        "content_sha256": hashlib.sha256(payload).hexdigest(),
    }


def observe_payload(root: Path) -> bool:
    return measure_payload(root)["passed"]


def measure_files_resolution(root: Path, nonce: str) -> dict:
    """Measure the files NSS backend and a nonce-bound absent-name control."""
    hosts = read_fixture(root, "etc/hosts", 65536).decode("utf-8")
    rows = [line.split("#", 1)[0].split() for line in hosts.splitlines()]
    declared = any(
        row and row[0] == "127.0.0.1" and "c2.dynamic.local" in row[1:] for row in rows
    )
    if not declared:
        return {"passed": False, "hosts_mapping": False}
    absent_name = f"absent-{hashlib.sha256(nonce.encode()).hexdigest()[:20]}.invalid"
    positive = subprocess.run(
        ["getent", "-s", "files", "hosts", "c2.dynamic.local"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    negative = subprocess.run(
        ["getent", "-s", "files", "hosts", absent_name],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    replies = [line.split() for line in positive.stdout.splitlines()]
    matches = bool(replies) and all(
        row[0] == "127.0.0.1" and "c2.dynamic.local" in row[1:] for row in replies
    )
    passed = (
        positive.returncode == 0
        and matches
        and negative.returncode == 2
        and not negative.stdout.strip()
    )
    return {
        "passed": passed,
        "hosts_mapping": True,
        "positive_returncode": positive.returncode,
        "positive_stdout": positive.stdout,
        "positive_stderr": positive.stderr,
        "negative_name": absent_name,
        "negative_returncode": negative.returncode,
        "negative_stdout": negative.stdout,
        "negative_stderr": negative.stderr,
    }


def observe_files_resolution(root: Path, nonce: str) -> bool:
    """Require both the local lookup and absent-name negative control."""
    return measure_files_resolution(root, nonce)["passed"]


def collect_observation(root: Path) -> dict:
    collection = read_fixture(root, "tmp/sticks_t1005/local_collection.txt", 131072)
    archive = read_fixture(root, "tmp/sticks_collected_data.tar.gz", 1048576)
    marker = read_fixture(root, "tmp/sticks_dynamic_resolution.txt", 4096)
    checks = {
        "collection_matches_declared_sources": observe_collection(root),
        "archive_contains_collection": observe_archive(root),
        "chunks_reassemble_archive": observe_chunks(root),
        "dynamic_resolution_recorded": b"127.0.0.1" in marker
        and b"c2.dynamic.local" in marker,
        "benign_transfer_retained": observe_payload(root),
    }
    return {
        "schema": "c0026-target-chain-observation/v1",
        "hostname": socket.gethostname(),
        "observer_uid": os.geteuid(),
        "boot_id": read_fixture(root, "proc/sys/kernel/random/boot_id", 256)
        .decode()
        .strip(),
        "collection_sha256": hashlib.sha256(collection).hexdigest(),
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "chunk_count": len(chunk_names(root)),
        "checks": checks,
        "passed": all(checks.values()),
        "scope": "Guest fixture chain only; no external exfiltration, historical fidelity, "
        "resource acquisition, or executor identity claim.",
    }


def main() -> int:
    observation = collect_observation(Path("/"))
    print(json.dumps(observation, sort_keys=True))
    return 0 if observation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
