#!/usr/bin/env python3
"""Collect unconstrained reconstructions from local models for later divergence analysis.

Same steps and declared environment as the finite-domain arm, but no catalog and no verifier.
One request per (campaign, model, sample) returns free-choice realizations for every step.
Raw structured outputs are written for inspection; the frozen divergence metric is defined
against the collected data, not before it.
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

from concretization.models import BindingCatalog  # noqa: E402
from concretization.provider import BudgetLedger, load_config, propose  # noqa: E402
from concretization.unconstrained_prompt import (  # noqa: E402
    SYSTEM_PROMPT_UNCONSTRAINED,
    build_unconstrained_prompt,
)
from contracts.procedural_ir import ProceduralPlan  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "release" / "experiments" / "unconstrained_divergence" / "reconstructions"
)
CAMPAIGNS = ("C0010", "C0026", "C0045")
CONFIGS = ("config.gpt-oss.local.json", "config.qwen-coder14.local.json")
SAMPLES_PER_MODEL = 3


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

    configs = [load_config(PROJECT_ROOT / name) for name in CONFIGS]
    with tempfile.TemporaryDirectory(prefix="sticks-unconstrained-") as scratch:
        scratch_dir = Path(scratch)
        for campaign_id in CAMPAIGNS:
            plan, catalog = _campaign_inputs(campaign_id)
            user_prompt = build_unconstrained_prompt(plan, catalog)
            for config in configs:
                budget = BudgetLedger(config.budget)
                for sample in range(1, SAMPLES_PER_MODEL + 1):
                    raw_dir = scratch_dir / campaign_id / config.model / str(sample)
                    call = propose(
                        config,
                        system_prompt=SYSTEM_PROMPT_UNCONSTRAINED,
                        user_prompt=user_prompt,
                        output_dir=raw_dir,
                        budget=budget,
                    )
                    # propose parses a "proposals" key; this arm uses "realizations", so read
                    # the persisted response and keep the free-form structure intact.
                    parsed = json.loads(
                        (raw_dir / "proposal_response.json").read_text(encoding="utf-8")
                    )
                    record = {
                        "campaign_id": campaign_id,
                        "model": config.model,
                        "sample": sample,
                        "temperature": config.temperature,
                        "realizations": parsed.get("realizations", []),
                        "raw_proposal_keys": sorted(parsed.keys()),
                        "response_sha256": call.response_sha256,
                    }
                    out = (
                        args.output_dir
                        / f"{campaign_id}.{config.model.replace(':', '_')}.{sample}.json"
                    )
                    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
                    print(
                        f"[collect] {campaign_id} {config.model} sample {sample}: "
                        f"{len(record['realizations'])} realizations, "
                        f"keys={record['raw_proposal_keys']}"
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
