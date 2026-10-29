"""Observed products bind bytes, not merely a capability name."""

import hashlib
import io
import tarfile

import pytest

from tests.test_probe_c0026_target import make_target
from scripts.probe_c0026_target import (
    measure_collection,
    measure_archive,
    measure_chunks,
)


def test_collection_measurement_binds_the_exact_compared_bytes(tmp_path):
    make_target(tmp_path)
    measured = measure_collection(tmp_path)
    content = (tmp_path / "tmp/sticks_t1005/local_collection.txt").read_bytes()
    assert measured["passed"] is True
    assert measured["content_sha256"] == hashlib.sha256(content).hexdigest()


def test_replacement_collection_has_a_different_consumer_input_digest(tmp_path):
    make_target(tmp_path)
    original = measure_collection(tmp_path)
    changed = b"UNOBSERVED REPLACEMENT COLLECTION"
    (tmp_path / "tmp/sticks_t1005/local_collection.txt").write_bytes(changed)
    with tarfile.open(tmp_path / "tmp/sticks_collected_data.tar.gz", "w:gz") as archive:
        member = tarfile.TarInfo("./local_collection.txt")
        member.size = len(changed)
        archive.addfile(member, io.BytesIO(changed))
    measured = measure_archive(tmp_path)
    assert measured["passed"] is True
    assert measured["input_sha256"] != original["content_sha256"]
    assert measure_collection(tmp_path)["passed"] is False


def test_chunk_measurement_binds_consumed_archive_bytes(tmp_path):
    make_target(tmp_path)
    archive = measure_archive(tmp_path)
    chunks = measure_chunks(tmp_path)
    assert chunks["passed"] is True
    assert chunks["input_sha256"] == archive["content_sha256"]


@pytest.mark.parametrize("duplicate_name", ["./local_collection.txt", "local_collection.txt",
                                             "././local_collection.txt"])
def test_archive_rejects_duplicate_member_with_conflicting_final_content(tmp_path, duplicate_name):
    make_target(tmp_path)
    expected = (tmp_path / "tmp/sticks_t1005/local_collection.txt").read_bytes()
    path = tmp_path / "tmp/sticks_collected_data.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, content in (("./local_collection.txt", expected),
                              (duplicate_name, b"different final collection")):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    with tarfile.open(path) as archive:
        assert archive.extractfile(archive.getmembers()[-1]).read() != expected
    with pytest.raises(ValueError, match="Duplicate collection archive member"):
        measure_archive(tmp_path)


def test_archive_checks_member_bounds_after_the_matching_member(tmp_path):
    make_target(tmp_path)
    expected = (tmp_path / "tmp/sticks_t1005/local_collection.txt").read_bytes()
    path = tmp_path / "tmp/sticks_collected_data.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, content in (("./local_collection.txt", expected),
                              ("oversized.txt", b"x" * 131073)):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    with pytest.raises(ValueError, match="bounded member contract"):
        measure_archive(tmp_path)
