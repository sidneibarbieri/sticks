"""A provider response without a JSON object is a malformed proposal, not a crash."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from curation.template_author import (  # noqa: E402
    AdmissionVocabulary,
    RejectionCode,
    admit_response,
    extract_proposal,
)


def test_a_json_object_is_extracted_from_surrounding_prose() -> None:
    assert extract_proposal('here it is {"a": 1} done') == {"a": 1}


def test_a_response_without_a_json_object_is_none() -> None:
    assert extract_proposal("the model refused and returned prose") is None


def test_an_empty_response_is_none() -> None:
    assert extract_proposal("") is None


def test_unbalanced_braces_are_none() -> None:
    assert extract_proposal("{ not json }") is None


def test_a_response_without_json_is_rejected_as_malformed_schema() -> None:
    vocabulary = AdmissionVocabulary(predicate_roles={}, bindable_kinds=frozenset())
    outcome = admit_response("T1105", "I cannot help with that.", vocabulary)
    assert not outcome.admitted
    assert outcome.rejection_code is RejectionCode.malformed_schema
