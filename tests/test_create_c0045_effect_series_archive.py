from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from scripts import create_c0045_effect_series_archive as creator


def test_archive_name_rejects_undeclared_roots(tmp_path: Path) -> None:
    path = tmp_path / "unexpected" / "record.json"
    path.parent.mkdir()
    path.write_text("{}")

    try:
        creator._archive_name(path, tmp_path, ("c0045-series-v1",))
    except ValueError as error:
        assert "declared archive roots" in str(error)
    else:
        raise AssertionError("undeclared roots must be rejected")


def test_regular_files_rejects_non_json_records(tmp_path: Path) -> None:
    record = tmp_path / "c0045-series-v1" / "b1-treatment" / "record.txt"
    record.parent.mkdir(parents=True)
    record.write_text("not evidence")

    try:
        creator._regular_files(tmp_path, ("c0045-series-v1",))
    except ValueError as error:
        assert "non-JSON" in str(error)
    else:
        raise AssertionError("non-JSON records must be rejected")


def test_archive_uses_no_extended_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = tmp_path / "c0045-series-v1" / "b1-treatment" / "selection.json"
    record.parent.mkdir(parents=True)
    record.write_text("{}")
    output = tmp_path / "series.tar.gz"
    monkeypatch.setattr(
        creator,
        "_verify_source_series",
        lambda _source, _series_path: creator.load_c0045_effect_series(),
    )

    def verify(archive_path: Path, _series_path: Path) -> None:
        with tarfile.open(archive_path, "r:gz") as archive:
            assert not archive.pax_headers
            assert all(not member.pax_headers for member in archive)

    monkeypatch.setattr(creator, "verify_archive", verify)

    creator.create_archive(tmp_path, output)

    assert output.is_file()
