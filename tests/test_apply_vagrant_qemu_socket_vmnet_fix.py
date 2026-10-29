"""Tests for the version-pinned vagrant-qemu transport repair."""

import pytest

from scripts.apply_vagrant_qemu_socket_vmnet_fix import (
    FD_SELECTION,
    STREAM_SELECTION,
    fixed_source,
)


def test_replaces_only_the_known_stream_selection():
    source = "before\n" + STREAM_SELECTION + "\nafter\n"

    assert fixed_source(source) == "before\n" + FD_SELECTION + "\nafter\n"


def test_is_idempotent_after_transport_is_fixed():
    source = "before\n" + FD_SELECTION + "\nafter\n"

    assert fixed_source(source) == source


def test_rejects_unrecognized_provider_source():
    with pytest.raises(RuntimeError, match="unexpected"):
        fixed_source("unrecognized source")
