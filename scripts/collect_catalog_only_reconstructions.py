#!/usr/bin/env python3
"""Collect catalog-only proposals: the catalog is supplied, admission is not applied.

This is the middle arm of the decomposition. The unconstrained arm removes both the catalog
and the verifier; the finite-domain arm applies both. Here the proposer receives exactly the
finite-domain prompt, so it sees the same catalog and the same declared environment, but
whatever it proposes is recorded as committed without passing the admission predicate.

Comparing the three arms separates two effects that the two-arm contrast conflates: how much
of the agreement comes from restricting the space of realizations, and how much comes from
deterministic admission on top of that restriction.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from concretization.prompt import SYSTEM_PROMPT, build_prompt  # noqa: E402
from concretization.provider import BudgetLedger, load_config, propose  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "release" / "experiments" / "unconstrained_divergence" / "catalog_only"
)
CAMPAIGNS = ("C0010", "C0026", "C0045")
CONFIGS = ("config.gpt-oss.local.json", "config.qwen-coder14.local.json")
SAMPLES_PER_MODEL = 3


def _load_templates() -> list[ActionTemplate]:
    payload = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    return [ActionTemplate.model_validate(item) for item in payload["templates"]]


def _campaign_inputs(campaign_id: str):
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
    )
    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
    )
    return plan, catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    templates = _load_templates()
    configs = [load_config(PROJECT_ROOT / name) for name in CONFIGS]
    with tempfile.TemporaryDirectory(prefix="sticks-catalog-only-") as scratch:
        scratch_dir = Path(scratch)
        for campaign_id in CAMPAIGNS:
            plan, catalog = _campaign_inputs(campaign_id)
            user_prompt = build_prompt(plan, catalog, templates)
            for config in configs:
                budget = BudgetLedger(config.budget)
                for sample in range(1, SAMPLES_PER_MODEL + 1):
                    call = propose(
                        config,
                        system_prompt=SYSTEM_PROMPT,
                        user_prompt=user_prompt,
                        output_dir=scratch_dir / campaign_id / config.model / str(sample),
                        budget=budget,
                    )
                    # Recorded as proposed: no admission predicate is applied in this arm.
                    record = {
                        "campaign_id": campaign_id,
                        "model": config.model,
                        "sample": sample,
                        "temperature": config.temperature,
                        "proposals": [
                            {
                                "technique_id": proposal.technique_id,
                                "template_id": proposal.template_id,
                                "bindings": proposal.bindings,
                            }
                            for proposal in call.proposals
                        ],
                        "malformed_proposals": call.malformed_proposals,
                    }
                    out = (
                        args.output_dir
                        / f"{campaign_id}.{config.model.replace(':', '_')}.{sample}.json"
                    )
                    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
                    print(
                        f"[catalog-only] {campaign_id} {config.model} sample {sample}: "
                        f"{len(record['proposals'])} proposals, "
                        f"{record['malformed_proposals']} malformed"
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
