#!/usr/bin/env python3
"""Admit proposed action templates and bind executable candidates to code witnesses."""

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

from concretization.models import ActionTemplate  # noqa: E402
from concretization.template_generation import (  # noqa: E402
    TemplateGenerationBatch,
    context_bindings_from_generation_batch,
)
from concretization.template_overlay import (  # noqa: E402
    TemplateImplementationWitness,
    build_template_overlay,
)


def _list_payload(path: Path, key: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get(key, []) if isinstance(payload, dict) else payload
    if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
        raise ValueError(f"{path} must contain a JSON list or an object with a {key} list")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-templates",
        type=Path,
        default=PROJECT_ROOT / "data/concretization/action_templates.json",
    )
    parser.add_argument("--generation-batch", type=Path, required=True)
    parser.add_argument("--witnesses", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-bound", action="store_true")
    args = parser.parse_args()

    base_templates = [
        ActionTemplate.model_validate(item)
        for item in _list_payload(args.base_templates, "templates")
    ]
    generation_batch = TemplateGenerationBatch.model_validate_json(
        args.generation_batch.read_text(encoding="utf-8")
    )
    witnesses = [
        TemplateImplementationWitness.model_validate(item)
        for item in _list_payload(args.witnesses, "witnesses")
    ]
    result = build_template_overlay(
        base_templates,
        generation_batch.templates,
        context_bindings_from_generation_batch(generation_batch),
        witnesses,
        artifact_root=args.artifact_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"[overlay] rejected: {result.rejected_count}")
    print(f"[overlay] planning only: {result.planning_only_count}")
    print(f"[overlay] implementation bound: {result.implementation_bound_count}")
    print(f"[overlay] hash: {result.content_sha256}")
    print(f"[overlay] output: {args.output}")
    if args.require_bound and not result.implementation_bound_templates:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
