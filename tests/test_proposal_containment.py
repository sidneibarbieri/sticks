"""The proposal-containment record is recomputable from the frozen v5 collection.

The record must agree with the cached cells it summarises, show no truncated generation, and
show that no inadmissible proposal reached a plan in the guarded arm.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COLLECTION = (
    PROJECT_ROOT
    / "release"
    / "experiments"
    / "controlled_comparison"
    / "prospective-qwen36-p17-v5-20261023"
)
RECORD = PROJECT_ROOT / "release" / "experiments" / "proposal_containment" / "v5.json"


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def _cells() -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((COLLECTION / "cache").glob("*.json"))
    ]


def test_record_is_bound_to_the_frozen_lock() -> None:
    lock_sha = hashlib.sha256((COLLECTION / "collection-lock.json").read_bytes()).hexdigest()
    assert _record()["collection_lock_sha256"] == lock_sha


def test_counts_recompute_from_cached_cells() -> None:
    record = _record()
    cells = _cells()
    assert record["cells_total"] == len(cells)
    for arm, summary in record["arms"].items():
        arm_cells = [cell for cell in cells if cell["arm_id"] == arm]
        inadmissible = [c for c in arm_cells if c["emitted"] and not c["oracle_admitted"]]
        assert summary["cells"] == len(arm_cells)
        assert summary["inadmissible_emitted"] == len(inadmissible)
        assert summary["refused"] == sum(1 for c in arm_cells if c["abstained"])


def test_no_generation_was_truncated() -> None:
    record = _record()
    assert record["generations_truncated"] == 0
    assert record["generations_stopped_normally"] == record["cells_total"]
    assert record["max_completion_tokens_observed"] < record["max_output_tokens"]


def test_guarded_arm_commits_no_inadmissible_proposal() -> None:
    record = _record()
    assert record["guarded_inadmissible_committed"] == 0
    assert record["guarded_refused"] == record["unguarded_inadmissible"]
    assert record["unguarded_inadmissible"] == (
        record["unguarded_unsatisfied_preconditions"] + record["unguarded_binding_kind_mismatch"]
    )
