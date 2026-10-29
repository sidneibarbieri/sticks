#!/usr/bin/env python3
"""Reconstruct an emulation plan for any ATT&CK campaign, in one command.

The recorded experiments show what this artifact measured. This runs the method on an input the
reader chooses: a campaign from the pinned bundle, a campaign from a bundle they supply, and
optionally their own model through a provider configuration.

The pipeline is the one the paper describes. A campaign is compiled into a procedural plan, the
minimal laboratory that plan can bind against is derived from the catalog rather than authored by
hand, and each step is concretized under deterministic admission. Steps with no admissible
realization are reported as such instead of being filled in, which is the behavior the paper claims.

Without a provider configuration the run is deterministic and offline: the finite-domain solver
proposes and the verifier admits. With one, a model proposes and the same verifier decides, so a
reader can substitute their own model without changing what admission means.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.lab_environment import derive_lab_environment  # noqa: E402
from concretization.models import ActionTemplate  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402

DEFAULT_BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
RULE = "-" * 78


def load_templates() -> list[ActionTemplate]:
    payload = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    return [ActionTemplate.model_validate(item) for item in payload["templates"]]


def compile_campaign(campaign: str, bundle: Path, destination: Path) -> ProceduralPlan:
    """Compile one campaign from a STIX bundle into the procedural plan the method consumes."""
    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "compile_stix_campaign.py"),
            campaign,
            "--bundle",
            str(bundle),
            "--output",
            str(destination),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return ProceduralPlan.model_validate_json(destination.read_text(encoding="utf-8"))


def concretize(plan_path: Path, bindings_path: Path, output: Path, config: Path | None) -> dict:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "concretize_procedural_plan.py"),
        "--plan", str(plan_path),
        "--bindings", str(bindings_path),
        "--templates", str(TEMPLATES_PATH),
        "--output", str(output),
        "--allow-unresolved",
    ]
    if config is not None:
        command += ["--config", str(config)]
    subprocess.run(command, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
    return json.loads(output.read_text(encoding="utf-8"))


def report(campaign: str, plan: ProceduralPlan, concretized: dict, config: Path | None) -> None:
    steps = concretized.get("steps", [])
    unresolved = concretized.get("unresolved_technique_ids", [])
    proposer = "your model, through the supplied configuration" if config else "the finite-domain solver, offline"

    print(RULE)
    print(f"CAMPAIGN {campaign}   steps in plan: {len(plan.steps)}   proposer: {proposer}")
    print(RULE)
    for step in steps:
        print(f"  admitted  {step['technique_id']:<14} -> {step['template_id']}")
    for technique in unresolved:
        print(f"  abstained {technique:<14} -> no admissible realization in the catalog")

    certificate = concretized.get("planning_certificate", {})
    print()
    print(f"  admitted {len(steps)} of {len(plan.steps)} steps; {len(unresolved)} left unresolved.")
    print(f"  causal certificate valid: {certificate.get('valid')}")
    print(
        "\n  A step with no admissible realization is reported, never invented. That is the"
        "\n  property the paper measures, applied here to the campaign you chose."
    )
    print(RULE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", help="ATT&CK campaign identifier, for example C0045")
    parser.add_argument("--bundle", default=str(DEFAULT_BUNDLE), help="STIX bundle to compile from")
    parser.add_argument("--config", help="provider configuration to let your own model propose")
    parser.add_argument("--output-dir", help="keep the generated plan, environment, and result")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = Path(args.config) if args.config else None
    if config is not None and not config.is_file():
        raise FileNotFoundError(f"provider configuration not found: {config}")

    with tempfile.TemporaryDirectory() as scratch:
        workdir = Path(args.output_dir) if args.output_dir else Path(scratch)
        workdir.mkdir(parents=True, exist_ok=True)
        plan_path = workdir / f"{args.campaign}.procedural-plan.json"
        bindings_path = workdir / f"{args.campaign}.binding-catalog.json"
        result_path = workdir / f"{args.campaign}.concretized-plan.json"

        plan = compile_campaign(args.campaign, Path(args.bundle), plan_path)
        templates = load_templates()
        environment = derive_lab_environment(f"{args.campaign}-lab", templates, plan)
        bindings_path.write_text(environment.model_dump_json(indent=2) + "\n", encoding="utf-8")
        concretized = concretize(plan_path, bindings_path, result_path, config)
        report(args.campaign, plan, concretized, config)
        if args.output_dir:
            print(f"  wrote {workdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
