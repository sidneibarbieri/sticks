#!/usr/bin/env python3
"""Report what the catalog's evidence policies certify, and refuse a policy that certifies nothing.

Requiring at least one evidence predicate per template is not enough to support an execution
claim. This step separates predicates that observe a declared effect from those that assert a
safety boundary or record only that a command ran, and fails when a template rests on the
latter alone.
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

from concretization.evidence_policy import audit_catalog, load_roles  # noqa: E402

CATALOG = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
ROLES = PROJECT_ROOT / "data" / "concretization" / "evidence_predicate_roles.json"
OUTPUT = PROJECT_ROOT / "release" / "experiments" / "evidence_policy" / "catalog.json"


def main() -> int:
    roles = load_roles(ROLES)
    templates = json.loads(CATALOG.read_text(encoding="utf-8"))["templates"]
    report = audit_catalog(templates, roles)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump() | {
        "question": (
            "Does every catalog template declare evidence that observes a state it produces, "
            "rather than only a safety boundary or the fact that a command ran?"
        ),
        "role_counts": {
            role: sum(1 for value in roles.values() if value.value == role)
            for role in ("effect", "safety", "liveness")
        },
        "registered_predicate_count": len(roles),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[evidence-policy] wrote {OUTPUT.relative_to(PROJECT_ROOT)}")
    print(
        f"[evidence-policy] {report.effect_certified_count}/{report.template_count} templates "
        "declare evidence observing a produced state"
    )

    for template_id in report.safety_only_templates:
        print(f"      certifies only safety boundaries: {template_id}")
    for template_id in report.liveness_only_templates:
        print(f"      rests on process exit alone: {template_id}")
    for predicate in report.unregistered_predicates:
        print(f"      predicate has no declared role: {predicate}")
    if not report.clean:
        raise SystemExit("[evidence-policy] catalog evidence standard not met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
