#!/usr/bin/env python3
"""Audit the versioned state-fact registry used by the STICKS planning boundary.

The result is a static identity-and-origin check. It does not execute a campaign,
contact a provider, or promote a planning fact to operational evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from concretization.fact_semantics import (  # noqa: E402
    FactSemanticsRegistry,
    build_fact_semantics_coverage_report,
)
from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402

DEFAULT_CATALOGS = (
    PROJECT_ROOT / "release/plans/C0010.binding-catalog.json",
    PROJECT_ROOT / "release/plans/C0026.binding-catalog.json",
    PROJECT_ROOT / "release/plans/C0045.binding-catalog.json",
)


def _load_templates(path: Path) -> list[ActionTemplate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_templates = payload.get("templates")
    if not isinstance(raw_templates, list):
        raise ValueError("action template catalog has no templates list")
    return [ActionTemplate.model_validate(item) for item in raw_templates]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=PROJECT_ROOT / "data/concretization/fact_semantics.json",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=PROJECT_ROOT / "data/concretization/action_templates.json",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        action="append",
        dest="catalogs",
        help="binding catalog to audit; repeat to select a different set",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    registry = FactSemanticsRegistry.model_validate_json(args.registry.read_text(encoding="utf-8"))
    templates = _load_templates(args.templates)
    catalog_paths = args.catalogs or list(DEFAULT_CATALOGS)
    catalogs = [
        BindingCatalog.model_validate_json(path.read_text(encoding="utf-8"))
        for path in catalog_paths
    ]
    report = build_fact_semantics_coverage_report(registry, catalogs, templates)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(report.model_dump_json(indent=2) + "\n")

    print(f"[fact-semantics] audited SUTs: {report.audited_sut_count}")
    print(f"[fact-semantics] conformant SUTs: {report.conformant_sut_count}")
    print(f"[fact-semantics] static only: {report.claim_boundary}")
    print(f"[fact-semantics] hash: {report.content_sha256}")
    print(f"[fact-semantics] output: {args.output}")
    return 0 if report.conformant else 1


if __name__ == "__main__":
    raise SystemExit(main())
