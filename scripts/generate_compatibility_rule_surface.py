#!/usr/bin/env python3
"""Render a reviewer-facing summary of CF/VMR/ID rule keywords and regexes."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_PATH = (
    PROJECT_ROOT / "measurement" / "sut" / "scripts" / "sut_measurement_pipeline.py"
)

RESULTS_MD = PROJECT_ROOT / "results" / "COMPATIBILITY_RULE_SURFACE.md"
RESULTS_JSON = PROJECT_ROOT / "results" / "compatibility_rule_surface.json"
RELEASE_MD = PROJECT_ROOT / "release" / "COMPATIBILITY_RULE_SURFACE.md"
RELEASE_JSON = PROJECT_ROOT / "release" / "compatibility_rule_surface.json"


def _load_pipeline_module():
    spec = importlib.util.spec_from_file_location("sticks_sut_measurement_pipeline", PIPELINE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _report_payload(module) -> dict[str, object]:
    return {
        "generated_from": "measurement/sut/scripts/sut_measurement_pipeline.py",
        "id_platform_keywords": sorted(module.ID_PLATFORM_KEYWORDS),
        "lateral_software_keywords": sorted(module.LATERAL_SOFTWARE_KEYWORDS),
        "kernel_boot_regex": module.KERNEL_BOOT_KEYWORDS.pattern,
        "vmr_permissions": sorted(module.VMR_PERMISSIONS),
        "vmr_name_regex": module.VMR_NAME_PATTERNS.pattern,
        "container_compatible_platforms": sorted(module.CONTAINER_COMPATIBLE_PLATFORMS),
        "default_fallback_class": "VMR",
    }


def _markdown_report(payload: dict[str, object]) -> str:
    return "\n".join(
        [
            "# Compatibility Rule Surface",
            "",
            "This report exposes the exact reviewer-facing keyword and regex surface",
            "behind the deterministic CF/VMR/ID compatibility rules used in the",
            "measurement pipeline. It is an audit aid; it does not introduce new",
            "measurements beyond the published rule-based classification.",
            "",
            "## Fixed Rule Inputs",
            "",
            f"- Generated from: `{payload['generated_from']}`",
            f"- Default fallback class: `{payload['default_fallback_class']}`",
            "",
            "## ID Platform Keywords",
            "",
            *(f"- `{item}`" for item in payload["id_platform_keywords"]),
            "",
            "## Lateral-Movement Software Keywords",
            "",
            *(f"- `{item}`" for item in payload["lateral_software_keywords"]),
            "",
            "## VMR Signals",
            "",
            f"- Kernel/boot regex: `{payload['kernel_boot_regex']}`",
            f"- Name-pattern regex: `{payload['vmr_name_regex']}`",
            f"- Privileged permissions: `{', '.join(payload['vmr_permissions'])}`",
            "",
            "## CF Platforms",
            "",
            f"- Container-compatible platforms: `{', '.join(payload['container_compatible_platforms'])}`",
            "",
        ]
    )


def main() -> int:
    module = _load_pipeline_module()
    payload = _report_payload(module)
    markdown = _markdown_report(payload) + "\n"

    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    RELEASE_MD.parent.mkdir(parents=True, exist_ok=True)

    RESULTS_MD.write_text(markdown, encoding="utf-8")
    RESULTS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    RELEASE_MD.write_text(markdown, encoding="utf-8")
    RELEASE_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"[OK] Results Markdown: {RESULTS_MD}")
    print(f"[OK] Results JSON: {RESULTS_JSON}")
    print(f"[OK] Release Markdown: {RELEASE_MD}")
    print(f"[OK] Release JSON: {RELEASE_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
