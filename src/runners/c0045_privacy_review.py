"""Bind a semantic C0045 privacy decision to an exact evidence archive."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from runners.capability_facts import Digest, ImmutableRecord
from scripts.screen_c0045_series_privacy import screen_archive


class C0045PrivacyReview(ImmutableRecord):
    schema_version: Literal["c0045-privacy-review/v1"]
    archive_sha256: Digest
    json_members: int = Field(strict=True, ge=1)
    lexical_screen_passed: Literal[True]
    reviewer_role: Literal["artifact_privacy_reviewer"]
    checked_categories: tuple[str, ...]
    approved_for_anonymous_review: Literal[True]
    approved_for_identified_release: Literal[False]


class C0045IdentifiedPrivacyReview(C0045PrivacyReview):
    """Preserve the privacy assessment and record a subsequent owner release grant."""

    schema_version: Literal["c0045-privacy-review/v2"]
    approved_for_identified_release: Literal[True]
    predecessor_review_sha256: Digest
    predecessor_review_json: str
    authorization_basis: Literal["explicit_owner_instruction"]
    authorization_reference: str = Field(min_length=20)


REQUIRED_CATEGORIES = frozenset({
    "credentials",
    "personal_identifiers",
    "tenant_or_organization_identifiers",
    "external_network_endpoints",
    "author_machine_paths",
})


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify_c0045_privacy_review(
    archive_path: Path, review_path: Path, *, require_identified: bool = False,
) -> C0045PrivacyReview | C0045IdentifiedPrivacyReview:
    """Reject a review that does not cover the exact clean archive."""
    payload = json.loads(review_path.read_bytes())
    model = (C0045IdentifiedPrivacyReview
             if payload.get("schema_version") == "c0045-privacy-review/v2"
             else C0045PrivacyReview)
    review = model.model_validate(payload)
    if require_identified and not review.approved_for_identified_release:
        raise ValueError("C0045 series is approved only for anonymous review")
    if isinstance(review, C0045IdentifiedPrivacyReview):
        predecessor_bytes = review.predecessor_review_json.encode("utf-8")
        if hashlib.sha256(predecessor_bytes).hexdigest() != review.predecessor_review_sha256:
            raise ValueError("C0045 predecessor privacy review digest differs")
        predecessor = C0045PrivacyReview.model_validate_json(predecessor_bytes)
        fields = C0045PrivacyReview.model_fields.keys() - {
            "schema_version", "approved_for_identified_release",
        }
        if any(getattr(predecessor, field) != getattr(review, field) for field in fields):
            raise ValueError("Identified release changed the predecessor privacy assessment")
    screen = screen_archive(archive_path)
    if not screen.passed:
        raise ValueError("C0045 archive fails the lexical privacy screen")
    if review.archive_sha256 != _sha256(archive_path):
        raise ValueError("C0045 privacy review covers a different archive")
    if review.json_members != screen.json_members:
        raise ValueError("C0045 privacy review member count differs from the archive")
    if set(review.checked_categories) != REQUIRED_CATEGORIES:
        raise ValueError("C0045 privacy review omits a required category")
    return review
