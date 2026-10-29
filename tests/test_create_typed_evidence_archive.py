"""The typed archive writer emits only portable, validated members."""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from scripts.create_typed_evidence_archive import create_archive


def staged_root(tmp_path: Path) -> Path:
    stage = tmp_path / "stage"
    for campaign in ("c0010", "c0026"):
        path = stage / campaign / "workspace" / "safe.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(campaign, encoding="utf-8")
    return stage


def test_creates_portable_archive_without_appledouble_members(tmp_path: Path) -> None:
    stage = staged_root(tmp_path)
    output = tmp_path / "evidence.tar.gz"

    create_archive(stage, output)

    with tarfile.open(output, mode="r:gz") as archive:
        names = [member.name for member in archive.getmembers()]
    assert "c0010" in names
    assert "c0026" in names
    assert all("._" not in name for name in names)


def test_archive_bytes_are_independent_of_the_output_name(tmp_path: Path) -> None:
    stage = staged_root(tmp_path)
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "other-name.tar.gz"

    create_archive(stage, first)
    create_archive(stage, second)

    assert first.read_bytes() == second.read_bytes()


def test_rejects_appledouble_metadata_in_staging(tmp_path: Path) -> None:
    stage = staged_root(tmp_path)
    (stage / "c0010" / "._safe.txt").write_text("metadata", encoding="utf-8")

    with pytest.raises(ValueError, match="Apple metadata"):
        create_archive(stage, tmp_path / "evidence.tar.gz")
