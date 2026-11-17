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
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.bundle_admission import BundleAdmissionError, admit_campaign  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402

DEFAULT_BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"
RULE = "-" * 78


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
    parser.add_argument(
        "--json-output",
        help="write the structured admission result, identical to the workbench download",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except BundleAdmissionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def run(args: argparse.Namespace) -> int:
    config = Path(args.config) if args.config else None
    if config is not None and not config.is_file():
        raise FileNotFoundError(f"provider configuration not found: {config}")

    with tempfile.TemporaryDirectory() as scratch:
        workdir = Path(args.output_dir) if args.output_dir else Path(scratch)
        workdir.mkdir(parents=True, exist_ok=True)
        plan, concretized, result = admit_campaign(
            PROJECT_ROOT, args.campaign, Path(args.bundle), workdir, config
        )
        report(args.campaign, plan, concretized, config)
        if args.json_output:
            Path(args.json_output).write_text(
                result.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        if args.output_dir:
            print(f"  wrote {workdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
