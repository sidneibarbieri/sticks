from __future__ import annotations

import json

import pytest

from runners.c0045_api_contract import MAX_RESPONSE_BYTES, responses_match

VERSION = '{"version":"2.9.0","service":"ray-dashboard"}'
JOBS = '{"auth":"disabled","jobs":[]}'


def test_valid_fixture_responses_match() -> None:
    assert responses_match(VERSION, JOBS)


@pytest.mark.parametrize(
    ("version_body", "jobs_body"),
    (
        ('{"version":"","service":"ray-dashboard"}', JOBS),
        (VERSION, '{"auth":"enabled","jobs":[]}'),
    ),
)
def test_semantically_invalid_fixture_responses_do_not_match(
    version_body: str, jobs_body: str
) -> None:
    assert not responses_match(version_body, jobs_body)


def test_malformed_fixture_response_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        responses_match("not json", JOBS)


def test_oversized_response_is_rejected() -> None:
    with pytest.raises(ValueError, match="size bound"):
        responses_match("x" * (MAX_RESPONSE_BYTES + 1), JOBS)
