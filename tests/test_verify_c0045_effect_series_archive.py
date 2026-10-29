from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from runners.c0045_effect_series import SERIES_PATH, SERIES_V2_PATH
from scripts import verify_c0045_effect_series_archive as verifier


def make_archive(
    path: Path, entries: tuple[tuple[str, bytes, bytes], ...]
) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, data, kind in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(data) if kind == tarfile.REGTYPE else 0
            archive.addfile(member, io.BytesIO(data) if data else None)


def test_archive_replays_every_selected_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "series.tar.gz"
    make_archive(archive_path, (
        ("./", b"", tarfile.DIRTYPE),
        ("./c0045-series-v1/b1-treatment/selection.json", b"{}", tarfile.REGTYPE),
    ))
    monkeypatch.setattr(
        verifier, "load_c0045_effect_series",
        lambda _series_path: SimpleNamespace(
            selected_cells=("b1-treatment", "b1-busy"),
            receipt_root_name="c0045-series-v1",
        ),
    )
    seen: list[str] = []

    def replay(root: Path, cell: str, _series_path: Path) -> SimpleNamespace:
        assert (root / "c0045-series-v1/b1-treatment/selection.json").is_file()
        seen.append(cell)
        return SimpleNamespace(
            status="observed" if cell == "b1-treatment" else "measured",
            boot_id=cell,
        )

    monkeypatch.setattr(verifier, "verify_c0045_series_cell", replay)
    audit = verifier.verify_archive(archive_path)

    assert seen == ["b1-treatment", "b1-busy"]
    assert audit.selected_cells == 2
    assert audit.unique_boots == 2
    assert audit.observed == 1
    assert audit.measured == 1
    assert audit.archive_sha256 == hashlib.sha256(archive_path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name,kind", (
    ("../escape", tarfile.REGTYPE),
    ("/absolute", tarfile.REGTYPE),
    ("c0045-series-v1/../escape", tarfile.REGTYPE),
    ("unexpected/file.json", tarfile.REGTYPE),
    ("c0045-series-v1/link", tarfile.SYMTYPE),
    ("c0045-series-v1/._selection.json", tarfile.REGTYPE),
    ("c0045-series-v1/.DS_Store", tarfile.REGTYPE),
))
def test_archive_rejects_unsafe_member(
    tmp_path: Path, name: str, kind: bytes
) -> None:
    archive_path = tmp_path / "unsafe.tar.gz"
    make_archive(archive_path, ((name, b"data", kind),))

    with pytest.raises(ValueError, match="archive contains"):
        verifier.verify_archive(archive_path)


def test_archive_rejects_duplicate_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicate.tar.gz"
    entry = ("c0045-series-v1/selection.json", b"{}", tarfile.REGTYPE)
    make_archive(archive_path, (entry, entry))

    with pytest.raises(ValueError, match="duplicate path"):
        verifier.verify_archive(archive_path)


def test_archive_rejects_extended_metadata(tmp_path: Path) -> None:
    archive_path = tmp_path / "extended.tar.gz"
    with tarfile.open(archive_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        member = tarfile.TarInfo("c0045-series-v1/selection.json")
        member.size = 2
        member.pax_headers = {"SCHILY.xattr.com.apple.provenance": "private"}
        archive.addfile(member, io.BytesIO(b"{}"))

    with pytest.raises(ValueError, match="extended metadata"):
        verifier.verify_archive(archive_path)


def test_archive_rejects_global_extended_metadata(tmp_path: Path) -> None:
    archive_path = tmp_path / "global-extended.tar.gz"
    with tarfile.open(
        archive_path,
        "w:gz",
        format=tarfile.PAX_FORMAT,
        pax_headers={"comment": "unreviewed metadata"},
    ) as archive:
        member = tarfile.TarInfo("c0045-series-v1/selection.json")
        member.size = 2
        archive.addfile(member, io.BytesIO(b"{}"))

    with pytest.raises(ValueError, match="global extended metadata"):
        verifier.verify_archive(archive_path)


def test_archive_rejects_reused_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "reused.tar.gz"
    make_archive(archive_path, (("c0045-series-v1/selection.json", b"{}", tarfile.REGTYPE),))
    monkeypatch.setattr(
        verifier, "load_c0045_effect_series",
        lambda _series_path: SimpleNamespace(
            selected_cells=("b1-treatment", "b1-busy"),
            receipt_root_name="c0045-series-v1",
        ),
    )
    monkeypatch.setattr(
        verifier, "verify_c0045_series_cell",
        lambda root, cell, _series_path: SimpleNamespace(
            status="measured", boot_id="same-boot"
        ),
    )

    with pytest.raises(ValueError, match="reuses a guest boot"):
        verifier.verify_archive(archive_path)


def test_archive_preserves_runner_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "error.tar.gz"
    make_archive(archive_path, (("c0045-series-v1/selection.json", b"{}", tarfile.REGTYPE),))
    monkeypatch.setattr(
        verifier, "load_c0045_effect_series",
        lambda _series_path: SimpleNamespace(
            selected_cells=("b1-treatment",), receipt_root_name="c0045-series-v1"
        ),
    )
    monkeypatch.setattr(
        verifier, "verify_c0045_series_cell",
        lambda root, cell, _series_path: SimpleNamespace(
            status="runner_error", boot_id=None
        ),
    )

    audit = verifier.verify_archive(archive_path)

    assert audit.runner_errors == 1
    assert audit.unique_boots == 0


@pytest.mark.parametrize("root,expected", (
    ("c0045-series-v1", SERIES_PATH),
    ("c0045-series-v2", SERIES_V2_PATH),
))
def test_archive_selects_series_from_its_root(
    tmp_path: Path, root: str, expected: Path
) -> None:
    archive_path = tmp_path / "series.tar.gz"
    make_archive(archive_path, ((f"{root}/selection.json", b"{}", tarfile.REGTYPE),))

    assert verifier.series_path_for_archive(archive_path) == expected


def test_archive_with_two_series_roots_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "both.tar.gz"
    make_archive(archive_path, (
        ("c0045-series-v1/selection.json", b"{}", tarfile.REGTYPE),
        ("c0045-series-v2/selection.json", b"{}", tarfile.REGTYPE),
    ))

    with pytest.raises(ValueError, match="no single declared series root"):
        verifier.series_path_for_archive(archive_path)
