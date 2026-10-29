from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest  # noqa: E402

from executors.local_transport_realizations import (  # noqa: E402
    BENIGN_PAYLOAD,
    REALIZATIONS,
    transfer_via_staging,
)


def _payload(tmp_path: Path) -> Path:
    payload = tmp_path / "payload.bin"
    payload.write_bytes(BENIGN_PAYLOAD)
    return payload


@pytest.mark.parametrize("template_id", sorted(REALIZATIONS))
def test_each_transport_delivers_the_payload(template_id, tmp_path):
    payload = _payload(tmp_path)
    destination = tmp_path / "out" / "delivered.bin"
    destination.parent.mkdir()

    result = REALIZATIONS[template_id](payload, destination)

    assert result.exit_code == 0
    assert destination.exists()
    expected = hashlib.sha256(BENIGN_PAYLOAD).hexdigest()
    assert result.destination_sha256 == expected
    # The evidence predicate (source/destination hashes match) holds for every transport.
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == expected


def test_staged_transport_removes_its_staging_file(tmp_path):
    payload = _payload(tmp_path)
    destination = tmp_path / "delivered.bin"

    transfer_via_staging(payload, destination)

    # End-state filesystem effect is the destination only; no staging residue remains.
    staging = destination.with_suffix(destination.suffix + ".staged")
    assert not staging.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["delivered.bin", "payload.bin"]
