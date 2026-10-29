#!/usr/bin/env python3
"""Re-verify Stage-2 template authoring offline, from the frozen proposer calls.

The proposer is untrusted and its calls are not reproducible, so its outputs are frozen once.
The gate is deterministic, so this step re-runs it over those frozen outputs and reproduces the
admit and reject counts on any machine without touching the API. This is the same trust
boundary the paper argues for procedures, applied to catalog authoring: the proposal is
recorded, the admission decision is recomputed.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from evaluation.technique_coverage import coverage_extension
from concretization.evidence_policy import load_roles  # noqa: E402
from curation.template_author import AdmissionVocabulary, admit_response  # noqa: E402

CALLS = PROJECT_ROOT / "release" / "experiments" / "stage2_authoring" / "calls"
PLANS = PROJECT_ROOT / "release" / "plans" / "enterprise"
CATALOG = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
ROLES = PROJECT_ROOT / "data" / "concretization" / "evidence_predicate_roles.json"
BASELINE = PROJECT_ROOT / "release" / "experiments" / "catalog_baseline" / "corpus.json"
RECORD = PROJECT_ROOT / "release" / "experiments" / "stage2_authoring" / "corpus.json"


def bindable_kinds() -> frozenset[str]:
    kinds: set[str] = set()
    for path in list(PLANS.glob("*.binding-catalog.json")) + list(
        (PROJECT_ROOT / "release" / "plans").glob("C00*.binding-catalog.json")
    ):
        for binding in json.loads(path.read_text(encoding="utf-8")).get("bindings", []):
            kinds.add(binding["kind"])
    return frozenset(kinds)


def step_counts() -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in PLANS.glob("*.procedural-plan.json"):
        for step in json.loads(path.read_text(encoding="utf-8"))["steps"]:
            counts[step["technique_id"]] += 1
    return counts


def frozen_response(call_dir: Path) -> str:
    raw = json.loads((call_dir / "provider_response.json").read_text(encoding="utf-8"))
    return raw["choices"][0]["message"]["content"]


def build_report() -> dict[str, object]:
    vocabulary = AdmissionVocabulary(
        predicate_roles=load_roles(ROLES), bindable_kinds=bindable_kinds()
    )
    counts = step_counts()

    admitted_techniques: set[str] = set()
    admitted = 0
    rejected: Counter[str] = Counter()
    for call_dir in sorted(CALLS.iterdir()):
        if not call_dir.is_dir():
            continue
        technique_id = call_dir.name.replace("_", ".")
        outcome = admit_response(technique_id, frozen_response(call_dir), vocabulary)
        if outcome.admitted:
            admitted += 1
            admitted_techniques.add(technique_id)
        else:
            rejected[outcome.rejection_code.value if outcome.rejection_code else "unknown"] += 1

    trusted = {
        technique
        for template in json.loads(CATALOG.read_text(encoding="utf-8"))["templates"]
        for technique in template["technique_ids"]
    }
    coverage = coverage_extension(counts, trusted, admitted_techniques)

    payload = {
        "question": (
            "Re-verified offline: how far does bounded proposal under deterministic admission "
            "extend contract-valid coverage, and does re-running the gate reproduce the verdicts?"
        ),
        "proposals": admitted + sum(rejected.values()),
        "admitted_templates": admitted,
        "rejected_templates": sum(rejected.values()),
        "rejected_by_code": dict(sorted(rejected.items())),
        **coverage,
        "matching_policy": "exact_technique_id",
        "evidence_tier": "schema_and_vocabulary_valid_draft",
        "note": (
            "Proposals are frozen untrusted outputs; the gate is recomputed here. Schema- and vocabulary-valid "
            "templates remain DRAFT; reach is not semantic or runtime validation. They are not promoted to the "
            "trusted catalog."
        ),
    }
    return payload


def main() -> int:
    payload = build_report()
    RECORD.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[stage2] re-verified {payload['proposals']} proposals: "
          f"{payload['admitted_templates']} schema/vocabulary-valid drafts, "
          f"exact reach {payload['trusted_contract_reach_steps']} -> "
          f"{payload['extended_contract_reach_steps']}/{payload['total_steps']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
