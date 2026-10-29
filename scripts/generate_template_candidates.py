#!/usr/bin/env python3
"""Generate bounded template candidates with a configured replay or hosted provider."""

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
from concretization.provider import load_config  # noqa: E402
from concretization.template_generation import (  # noqa: E402
    TemplateGenerationTarget,
    generate_template_candidates,
)


def _object_list(path: Path, key: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get(key, []) if isinstance(payload, dict) else payload
    if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
        raise ValueError(f"{path} must contain a JSON list or an object with a {key} list")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument(
        "--templates",
        type=Path,
        default=PROJECT_ROOT / "data/concretization/action_templates.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-attempts-per-target", type=int, default=3)
    parser.add_argument("--require-admitted", action="store_true")
    args = parser.parse_args()

    templates = [
        ActionTemplate.model_validate(item) for item in _object_list(args.templates, "templates")
    ]
    targets = [
        TemplateGenerationTarget.model_validate(item)
        for item in _object_list(args.targets, "targets")
    ]
    result = generate_template_candidates(
        targets,
        templates,
        load_config(args.config),
        output_dir=args.output_dir,
        max_attempts_per_target=args.max_attempts_per_target,
    )
    output_path = args.output_dir / "template-candidates.json"
    output_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"[template-generation] targets: {result.target_count}")
    print(f"[template-generation] requests: {result.request_count}")
    print(f"[template-generation] admitted candidates: {result.admitted_count}")
    print(f"[template-generation] estimated USD: {result.estimated_usd:.8f}")
    print(f"[template-generation] hash: {result.content_sha256}")
    print(f"[template-generation] output: {output_path}")
    if args.require_admitted and not result.templates:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
