from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from runners import c0045_privacy_review as review_module


def _review(archive: Path, **changes: object) -> Path:
    payload = {
        "schema_version": "c0045-privacy-review/v1",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "json_members": 2,
        "lexical_screen_passed": True,
        "reviewer_role": "artifact_privacy_reviewer",
        "checked_categories": sorted(review_module.REQUIRED_CATEGORIES),
        "approved_for_anonymous_review": True,
        "approved_for_identified_release": False,
    }
    payload.update(changes)
    path = archive.with_suffix(".review.json")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_matching_review_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "series.tar.gz"
    archive.write_bytes(b"sealed")
    monkeypatch.setattr(review_module, "screen_archive", lambda _: SimpleNamespace(passed=True, json_members=2))

    review = review_module.verify_c0045_privacy_review(archive, _review(archive))

    assert review.approved_for_anonymous_review


def test_review_rejects_other_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "series.tar.gz"
    archive.write_bytes(b"sealed")
    other = tmp_path / "other.tar.gz"
    other.write_bytes(b"different")
    monkeypatch.setattr(review_module, "screen_archive", lambda _: SimpleNamespace(passed=True, json_members=2))

    with pytest.raises(ValueError, match="different archive"):
        review_module.verify_c0045_privacy_review(archive, _review(other))
