"""Independent C0026 guest-chain observation fixtures."""

import io
from pathlib import Path
import tarfile

from scripts.probe_c0026_target import collect_observation


def write_fixture(root: Path, relative: str, content: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def make_target(root: Path) -> None:
    notes = b"Controlled note.\n"
    report = b"Synthetic report.\n"
    collection = b"andromeda_notes.txt\n" + notes + b"\nreport_2021.txt\n" + report
    write_fixture(root, "home/ubuntu/andromeda_notes.txt", notes)
    write_fixture(root, "home/ubuntu/staged_docs/report_2021.txt", report)
    write_fixture(root, "tmp/sticks_t1005/local_collection.txt", collection)
    write_fixture(root, "tmp/sticks_dynamic_resolution.txt", b"127.0.0.1 c2.dynamic.local\n")
    write_fixture(root, "tmp/sticks_downloaded_payload.sh", b"#!/bin/sh\necho STICKS benign payload\n")
    write_fixture(root, "proc/sys/kernel/random/boot_id", b"synthetic-boot-id\n")
    archive_path = root / "tmp/sticks_collected_data.tar.gz"
    with tarfile.open(archive_path, "w:gz") as package:
        member = tarfile.TarInfo("./local_collection.txt")
        member.size = len(collection)
        package.addfile(member, io.BytesIO(collection))
    archive = archive_path.read_bytes()
    for index, offset in enumerate(range(0, len(archive), 128)):
        write_fixture(root, f"tmp/sticks_chunk.{index:02d}", archive[offset : offset + 128])


def test_c0026_probe_accepts_bound_guest_chain(tmp_path: Path) -> None:
    make_target(tmp_path)

    observation = collect_observation(tmp_path)

    assert observation["passed"]
    assert all(observation["checks"].values())
    assert observation["chunk_count"] >= 2


def test_c0026_probe_rejects_drifted_archive_chunk(tmp_path: Path) -> None:
    make_target(tmp_path)
    (tmp_path / "tmp/sticks_chunk.00").write_bytes(b"changed")

    observation = collect_observation(tmp_path)

    assert not observation["passed"]
    assert not observation["checks"]["chunks_reassemble_archive"]
