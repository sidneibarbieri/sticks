#!/usr/bin/env python3
"""Report the contract strength of the catalog, and refuse an over-admitting contract.

The evidence-policy report checks that a template's declared evidence observes a state it
produces. It does not check the shape of the contract. A template can carry a proper effect
predicate and still over-admit: it can produce a state while requiring nothing (it would be
admitted in any state), or its required facts can all be ones it produces itself (the
precondition carries no independent constraint). This step audits both patterns on the frozen
catalog and fails when any template matches, so a weak contract cannot widen admission
silently when templates are imported or proposed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from concretization.contract_strength import audit_catalog_contracts  # noqa: E402

CATALOG = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
OUTPUT = PROJECT_ROOT / "release" / "experiments" / "contract_strength" / "catalog.json"


def main() -> int:
    templates = json.loads(CATALOG.read_text(encoding="utf-8"))["templates"]
    report = audit_catalog_contracts(templates)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump() | {
        "question": (
            "Does every catalog template condition its produced state on at least one fact it "
            "does not itself produce, so the deterministic verifier cannot admit it unconditionally "
            "or circularly?"
        ),
        "sound_contract_count": report.template_count
        - len(set(report.unconditioned_effect_templates) | set(report.self_satisfying_templates)),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[contract-strength] wrote {OUTPUT.relative_to(PROJECT_ROOT)}")
    print(
        f"[contract-strength] {payload['sound_contract_count']}/{report.template_count} templates "
        "declare a sound contract"
    )
    for template_id in report.unconditioned_effect_templates:
        print(f"      unconditioned effect (produces a state with no precondition): {template_id}")
    for template_id in report.self_satisfying_templates:
        print(f"      self-satisfying requirement (requires only facts it produces): {template_id}")
    if not report.clean:
        print("[contract-strength][FAIL] the catalog contains an over-admitting contract", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
