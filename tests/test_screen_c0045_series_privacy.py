from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import screen_c0045_series_privacy as privacy_screen


def _archive(path: Path, document: object) -> None:
    data = json.dumps(document).encode("utf-8")
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("c0045-series-v1/cell/record.json")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))


def test_clean_archive_reports_digest_and_manual_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "series.tar.gz"
    _archive(path, {"host": "target-linux-1", "cpu_seconds": 1.25})
    monkeypatch.setattr(
        privacy_screen, "verify_archive", lambda *_: SimpleNamespace(archive_sha256="0" * 64)
    )

    result = privacy_screen.screen_archive(path)

    assert result.archive_sha256 == "0" * 64
    assert result.json_members == 1
    assert result.passed
    assert result.findings == {}


@pytest.mark.parametrize("document,expected", [
    ({"tenant_id": "opaque"}, "tenant_field"),
    ({"metadata": {"password": "sensitive"}}, "secret_field"),
    ({"stderr": "contact person@example.org"}, "email"),
    ({"path": "/Users/researcher/run"}, "mac_home"),
    ({"source_ip": "10.0.0.8"}, "ipv4"),
    ({"command": "https://internal.example.org"}, "url"),
])
def test_sensitive_values_are_reported_without_printing_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, document: object, expected: str
) -> None:
    path = tmp_path / "series.tar.gz"
    _archive(path, document)
    monkeypatch.setattr(
        privacy_screen, "verify_archive", lambda *_: SimpleNamespace(archive_sha256="0" * 64)
    )

    result = privacy_screen.screen_archive(path)

    assert not result.passed
    assert result.findings[expected] > 0


def test_non_json_member_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "series.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("c0045-series-v1/cell/debug.log")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    monkeypatch.setattr(
        privacy_screen, "verify_archive", lambda *_: SimpleNamespace(archive_sha256="0" * 64)
    )

    with pytest.raises(ValueError, match="non-JSON"):
        privacy_screen.screen_archive(path)


def test_series_path_reaches_archive_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "series.tar.gz"
    _archive(path, {"host": "target-linux-1"})
    series_path = tmp_path / "series-v2.json"
    seen: list[Path] = []

    def verify(_: Path, selected: Path) -> SimpleNamespace:
        seen.append(selected)
        return SimpleNamespace(archive_sha256="0" * 64)

    monkeypatch.setattr(privacy_screen, "verify_archive", verify)

    privacy_screen.screen_archive(path, series_path)

    assert seen == [series_path]
