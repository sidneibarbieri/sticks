"""Host and guest C0045 fixture contracts must not silently drift."""

import pytest

from runners.c0045_fixture_contract import (
    MAX_FIXTURE_BYTES,
    TOOLKIT_SHA256,
    TRANSFER_PAYLOAD,
    TRANSFER_SHA256,
    execution_trace_path,
)
from scripts import probe_shadowray_target as probe


def test_guest_probe_constants_match_host_contract() -> None:
    assert probe.MAX_FIXTURE_BYTES == MAX_FIXTURE_BYTES
    assert probe.TRANSFER_PAYLOAD == TRANSFER_PAYLOAD
    assert probe.TOOLKIT_SHA256 == TOOLKIT_SHA256


def test_transfer_digest_matches_declared_payload() -> None:
    import hashlib

    assert hashlib.sha256(TRANSFER_PAYLOAD).hexdigest() == TRANSFER_SHA256


def test_trace_path_requires_a_fixed_nonce_shape() -> None:
    assert execution_trace_path("a" * 32).endswith("a" * 32 + ".trace")
    with pytest.raises(ValueError, match="Invalid trace"):
        execution_trace_path("not-a-nonce")
