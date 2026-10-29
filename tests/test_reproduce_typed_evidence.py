"""The reviewer gate must require evidence for manuscript QEMU claims."""

from pathlib import Path

import pytest

from scripts import reproduce


def test_manuscript_with_typed_outcomes_requires_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manuscript = tmp_path / "main.tex"
    manuscript.write_text(
        r"\input{results/typed_campaign_outcomes.tex}", encoding="utf-8"
    )
    monkeypatch.setattr(reproduce, "TYPED_EVIDENCE_PATH", tmp_path / "missing.tar.gz")

    with pytest.raises(FileNotFoundError, match="typed-run evidence archive"):
        reproduce._require_manuscript_evidence(manuscript)


def test_other_manuscripts_do_not_require_typed_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manuscript = tmp_path / "main.tex"
    manuscript.write_text("% \\input{results/typed_campaign_outcomes.tex}\nText", encoding="utf-8")
    monkeypatch.setattr(reproduce, "TYPED_EVIDENCE_PATH", tmp_path / "missing.tar.gz")

    reproduce._require_manuscript_evidence(manuscript)


def test_typed_archive_is_accepted_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manuscript = tmp_path / "main.tex"
    manuscript.write_text(
        r"\input { results/typed_campaign_outcomes.tex }", encoding="utf-8"
    )
    archive = tmp_path / "typed.tar.gz"
    archive.touch()
    monkeypatch.setattr(reproduce, "TYPED_EVIDENCE_PATH", archive)

    reproduce._require_manuscript_evidence(manuscript)


def test_c0045_archive_is_replayed_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "series.tar.gz"
    archive.touch()
    commands: list[list[str]] = []
    monkeypatch.setattr(reproduce, "C0045_SERIES_ARCHIVE_PATH", archive)
    monkeypatch.setattr(reproduce, "_run", commands.append)

    reproduce._verify_c0045_series_if_present()

    assert commands == [
        [reproduce.sys.executable, "-m", module, "--archive", str(archive)]
        for module in (
            "scripts.verify_c0045_effect_series_archive",
            "scripts.screen_c0045_series_privacy",
        )
    ]


def test_c0045_archive_is_not_implied_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reproduce, "C0045_SERIES_ARCHIVE_PATH", tmp_path / "missing.tar.gz")
    monkeypatch.setattr(
        reproduce, "_run", lambda command: pytest.fail(f"Unexpected run: {command}")
    )

    reproduce._verify_c0045_series_if_present()


def test_typed_reference_uses_pinned_manifest_only_when_bundled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = tmp_path / "reference.json"
    bound_reference = tmp_path / "bound-reference.json"
    monkeypatch.setattr(reproduce, "TYPED_REFERENCE_MANIFEST_PATH", reference)
    monkeypatch.setattr(
        reproduce, "TYPED_BOUND_REFERENCE_MANIFEST_PATH", bound_reference
    )

    assert reproduce._typed_reference_args() == [
        "--reference-root", str(reproduce.PROJECT_ROOT)
    ]

    reference.write_bytes(b"pinned manifest")
    assert reproduce._typed_reference_args() == [
        "--known-reference-manifest", str(reference)
    ]

    bound_reference.write_bytes(b"bound manifest")
    assert reproduce._typed_reference_args() == [
        "--bound-reference-manifest", str(bound_reference)
    ]
