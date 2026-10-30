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


@pytest.mark.parametrize("mutation", (None, "unbound_predecessor", "changed_assessment", "missing_grant"))
def test_identified_release_preserves_privacy_assessment_and_requires_owner_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str | None,
) -> None:
    archive = tmp_path / "series.tar.gz"
    archive.write_bytes(b"sealed")
    predecessor = _review(archive).read_text()
    payload = json.loads(predecessor)
    payload.update({
        "schema_version": "c0045-privacy-review/v2",
        "approved_for_identified_release": True,
        "predecessor_review_json": predecessor,
        "predecessor_review_sha256": hashlib.sha256(predecessor.encode()).hexdigest(),
        "authorization_basis": "explicit_owner_instruction",
        "authorization_reference": "Owner explicitly approved this identified archive release.",
    })
    if mutation == "unbound_predecessor":
        payload["predecessor_review_sha256"] = "a" * 64
    elif mutation == "changed_assessment":
        payload["json_members"] = 3
    elif mutation == "missing_grant":
        del payload["authorization_basis"]
    path = tmp_path / "identified.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(review_module, "screen_archive", lambda _: SimpleNamespace(passed=True, json_members=2))
    if mutation is None:
        assert review_module.verify_c0045_privacy_review(
            archive, path, require_identified=True,
        ).approved_for_identified_release
    else:
        with pytest.raises(ValueError):
            review_module.verify_c0045_privacy_review(archive, path, require_identified=True)


def test_anonymous_review_cannot_authorize_identified_release(tmp_path: Path):
    archive = tmp_path / "series.tar.gz"
    archive.write_bytes(b"sealed")
    with pytest.raises(ValueError, match="approved only for anonymous review"):
        review_module.verify_c0045_privacy_review(archive, _review(archive), require_identified=True)
