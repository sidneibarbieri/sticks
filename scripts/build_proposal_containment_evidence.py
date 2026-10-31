#!/usr/bin/env python3
"""Measure how often real model proposals violate the declared contract, and what admission does.

The frozen v5 collection runs one local model over the same steps in three arms: a
catalog-constrained prior-work-style planner, the STICKS proposer without the verifier, and
the STICKS proposer with the verifier. Every cell keeps its raw request, raw response and
admission verdict. This step reads those cached records and counts, per arm, the proposals
the deterministic verifier finds inadmissible and the typed reasons it gives.

The informative quantity is the violation rate of an unguarded proposer, not the validity of
the guarded arm: the guarded arm is scored by its own verifier, so its rate is circular by
construction and is reported only as the count of proposals it refused. Every generation is
also checked for truncation, because a proposal cut off by the token cap would be recorded
as a refusal it never earned.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "prospective-qwen36-p17-v5-20261023"
COLLECTION = PROJECT_ROOT / "release" / "experiments" / "controlled_comparison" / EXPERIMENT_ID
OUTPUT = PROJECT_ROOT / "release" / "experiments" / "proposal_containment" / "v5.json"
ARMS = ("prior_work_style", "sticks_without_admission", "sticks_admitted")


def _response(record: dict) -> dict:
    body = record["generation"]["response_body"]
    return json.loads(body) if isinstance(body, str) else body


def main() -> int:
    lock_bytes = (COLLECTION / "collection-lock.json").read_bytes()
    lock = json.loads(lock_bytes)
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((COLLECTION / "cache").glob("*.json"))
    ]
    arms: dict[str, dict] = {}
    for arm in ARMS:
        cells = [record for record in records if record["arm_id"] == arm]
        inadmissible = [
            record for record in cells if record["emitted"] and not record["oracle_admitted"]
        ]
        reasons = Counter(code for record in inadmissible for code in record["issue_codes"])
        arms[arm] = {
            "cells": len(cells),
            "emitted": sum(1 for record in cells if record["emitted"]),
            "admitted_by_verifier": sum(1 for record in cells if record["oracle_admitted"]),
            "inadmissible_emitted": len(inadmissible),
            "refused": sum(1 for record in cells if record["abstained"]),
            "parse_errors": sum(1 for record in cells if record["parse_error"]),
            "inadmissible_reasons": dict(sorted(reasons.items())),
        }
    responses = [_response(record) for record in records]
    stop_reasons = Counter(str(response.get("done_reason")) for response in responses)
    payload = {
        "question": (
            "How often does a real local-model proposer, given the catalog, propose an action that "
            "violates the declared contract, and does admission keep those proposals out of the plan?"
        ),
        "experiment_id": EXPERIMENT_ID,
        "collection_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "model": lock["model"],
        "thinking_mode": lock["thinking_mode"],
        "temperature": lock["temperature"],
        "max_output_tokens": lock["max_output_tokens"],
        "campaigns": lock["campaigns"],
        "seeds": lock["seeds"],
        "cells_total": len(records),
        "cells_per_arm": len(records) // len(ARMS),
        "arms": arms,
        "unguarded_inadmissible": arms["sticks_without_admission"]["inadmissible_emitted"],
        "unguarded_unsatisfied_preconditions": arms["sticks_without_admission"][
            "inadmissible_reasons"
        ].get("UNSATISFIED_PRECONDITIONS", 0),
        "unguarded_binding_kind_mismatch": arms["sticks_without_admission"][
            "inadmissible_reasons"
        ].get("BINDING_KIND_MISMATCH", 0),
        "prior_work_inadmissible": arms["prior_work_style"]["inadmissible_emitted"],
        "guarded_refused": arms["sticks_admitted"]["refused"],
        "guarded_inadmissible_committed": arms["sticks_admitted"]["inadmissible_emitted"],
        "generation_stop_reasons": dict(sorted(stop_reasons.items())),
        "generations_stopped_normally": stop_reasons.get("stop", 0),
        "generations_truncated": stop_reasons.get("length", 0),
        "max_completion_tokens_observed": max(
            int(response.get("eval_count") or 0) for response in responses
        ),
        "boundary": (
            "One local model, temperature 0.2, thinking off, three fully supported campaigns. The "
            "guarded arm's validity is circular and is not reported as a rate. The prior-work-style "
            "arm is catalog-constrained and lacks the prior system's execution-feedback loop. No "
            "comparative operational claim follows."
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[proposal-containment] wrote {OUTPUT.relative_to(PROJECT_ROOT)}")
    print(
        f"[proposal-containment] unguarded proposer: {payload['unguarded_inadmissible']}/"
        f"{arms['sticks_without_admission']['cells']} inadmissible; guarded arm refused "
        f"{payload['guarded_refused']} and committed {payload['guarded_inadmissible_committed']}"
    )
    print(
        f"[proposal-containment] {payload['generations_stopped_normally']}/{payload['cells_total']} "
        f"generations stopped normally, {payload['generations_truncated']} truncated"
    )
    if payload["generations_truncated"]:
        print("[proposal-containment][FAIL] a truncated generation would masquerade as a refusal")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
