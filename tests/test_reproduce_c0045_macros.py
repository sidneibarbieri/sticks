"""The reviewer gate must bind the paper's C0045 numbers to the archive."""

from pathlib import Path

import pytest

from scripts import reproduce


def test_manuscript_c0045_macros_require_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manuscript = tmp_path / "main.tex"
    manuscript.write_text(r"\input{results/c0045_series_macros.tex}", encoding="utf-8")
    monkeypatch.setattr(reproduce, "C0045_SERIES_ARCHIVE_PATH", tmp_path / "missing.tar.gz")

    with pytest.raises(FileNotFoundError, match="C0045 observer calibration"):
        reproduce._verify_c0045_paper_macros(manuscript)


def test_manuscript_c0045_macros_must_match_the_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manuscript = tmp_path / "main.tex"
    manuscript.write_text(r"\input{results/c0045_series_macros.tex}", encoding="utf-8")
    (tmp_path / "results").mkdir()
    (tmp_path / "results/c0045_series_macros.tex").write_text("stale\n", encoding="utf-8")
    archive = tmp_path / "series.tar.gz"
    archive.touch()
    monkeypatch.setattr(reproduce, "C0045_SERIES_ARCHIVE_PATH", archive)
    monkeypatch.setattr(
        reproduce.subprocess, "run",
        lambda *_args, **_kwargs: reproduce.subprocess.CompletedProcess([], 0, "fresh\n", ""),
    )

    with pytest.raises(ValueError, match="differs from the C0045 archive"):
        reproduce._verify_c0045_paper_macros(manuscript)
