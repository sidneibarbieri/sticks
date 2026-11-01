"""Reject altered populations and evidence before journal interpretation."""

import hashlib
import json

import pytest

from scripts.verify_caldera_integration_archive import (
    require_distinct_runs,
    verify_evidence_hashes,
)


def test_hash_gate_rejects_changed_or_additional_evidence(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    receipt = evidence / "receipt.json"
    receipt.write_bytes(b'{"passed":true}')
    manifest = {receipt.name: hashlib.sha256(receipt.read_bytes()).hexdigest()}
    (tmp_path / "evidence-sha256.json").write_text(json.dumps(manifest))
    assert verify_evidence_hashes(tmp_path) == 1

    receipt.write_bytes(b'{"passed":false}')
    with pytest.raises(ValueError, match="digest differs"):
        verify_evidence_hashes(tmp_path)

    receipt.write_bytes(b'{"passed":true}')
    (evidence / "unexpected.json").write_text("{}")
    with pytest.raises(ValueError, match="population differs"):
        verify_evidence_hashes(tmp_path)


def test_hash_gate_rejects_missing_evidence(tmp_path):
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence-sha256.json").write_text(
        json.dumps({"missing.json": "0" * 64})
    )
    with pytest.raises(ValueError, match="population differs"):
        verify_evidence_hashes(tmp_path)


@pytest.mark.parametrize("shared_identity", ["run_id", "target_boot_id"])
def test_repetition_rejects_copied_run_or_reused_guest(shared_identity):
    first = {"run_id": "run-one", "target_boot_id": "boot-one"}
    second = {"run_id": "run-two", "target_boot_id": "boot-two"}
    require_distinct_runs([first, second])
    second[shared_identity] = first[shared_identity]
    with pytest.raises(ValueError, match=shared_identity):
        require_distinct_runs([first, second])
