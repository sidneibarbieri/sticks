#!/usr/bin/env python3
"""Emit proposer-convergence evidence from live local-model proposals.

For each deep campaign the finite-domain solver commits a reference execution with no
proposal. Local models then propose realizations at temperature 0.7; each proposal passes
the same deterministic verifier over the same finite catalog. The record holds one hash per
observation, so a reader checks convergence directly.

This step needs local models (an Ollama endpoint exposing an OpenAI-compatible API) and is
therefore not part of the offline deterministic reproduction. A reviewer with the models can
regenerate the records; without them, the frozen records stand as the recorded outcome.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import json  # noqa: E402

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from concretization.pipeline import action_catalog_hash  # noqa: E402
from concretization.prompt import SYSTEM_PROMPT, build_prompt  # noqa: E402
from concretization.proposer_convergence import (  # noqa: E402
    ControlledConditions,
    assemble_record,
    model_observation,
    solver_observation,
)
from concretization.provider import (  # noqa: E402
    BudgetLedger,
    ProviderConfig,
    load_config,
    propose,
)
from contracts.procedural_ir import ProceduralPlan  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "release" / "experiments" / "proposer_convergence"
CAMPAIGNS = ("C0010", "C0026", "C0045")

QUESTION = "Does the verified procedure depend on which proposer supplied it?"
NOTE = (
    "Local models are sampled at temperature 0.7, so proposals vary between runs while the "
    "committed plan does not. Convergence is a property of the verifier over a finite "
    "catalog, not agreement between models."
)
HELD_CONSTANT = [
    "system prompt",
    "action catalog",
    "binding catalog",
    "procedural plan",
    "temperature",
    "max output tokens",
    "verifier version",
    "admissibility scope",
]
VARIED_ACROSS_RUNS = ["model", "sampling seed (implicit, temperature 0.7)"]
RETRY_POLICY = (
    "none: a single request per run, and a malformed or inadmissible proposal is rejected "
    "rather than retried"
)

# One model is sampled twice and a second family once, so the record shows convergence is
# not a single-sample coincidence and holds across model families.
PROPOSER_PLAN = [
    ("config.gpt-oss.local.json", 2),
    ("config.qwen-coder14.local.json", 1),
]


def _load_templates() -> list[ActionTemplate]:
    payload = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    return [ActionTemplate.model_validate(item) for item in payload["templates"]]


def _shared_setting(configs: list[ProviderConfig], attribute: str):
    values = {getattr(config, attribute) for config in configs}
    if len(values) != 1:
        raise ValueError(f"proposers disagree on {attribute}: {sorted(values)}")
    return values.pop()


def _conditions(
    templates: list[ActionTemplate], configs: list[ProviderConfig]
) -> ControlledConditions:
    return ControlledConditions(
        action_catalog_sha256=action_catalog_hash(templates),
        system_prompt_sha256=hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        temperature=_shared_setting(configs, "temperature"),
        max_output_tokens=_shared_setting(configs, "max_output_tokens"),
        retry_policy=RETRY_POLICY,
        held_constant=HELD_CONSTANT,
        varied_across_runs=VARIED_ACROSS_RUNS,
    )


def _campaign_inputs(campaign_id: str):
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
    )
    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
    )
    return plan, catalog


def _model_slug(model: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in model).strip("-")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    templates = _load_templates()
    proposers = [(load_config(PROJECT_ROOT / name), samples) for name, samples in PROPOSER_PLAN]
    conditions = _conditions(templates, [config for config, _ in proposers])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for campaign_id in CAMPAIGNS:
        plan, catalog = _campaign_inputs(campaign_id)
        user_prompt = build_prompt(plan, catalog, templates)
        observations = [solver_observation(plan, catalog, templates)]
        for config, sample_count in proposers:
            budget = BudgetLedger(config.budget)
            for sample in range(1, sample_count + 1):
                call_dir = (
                    args.output_dir
                    / "calls"
                    / campaign_id
                    / _model_slug(config.model)
                    / str(sample)
                )
                if call_dir.exists():
                    raise FileExistsError(f"refusing to replace recorded call: {call_dir}")
                call = propose(
                    config,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    output_dir=call_dir,
                    budget=budget,
                )
                call_record_path = call_dir / "call_record.json"
                call_record_path.write_text(call.model_dump_json(indent=2) + "\n", encoding="utf-8")
                observations.append(
                    model_observation(
                        plan,
                        catalog,
                        templates,
                        call.proposals,
                        proposer=config.model,
                        temperature=config.temperature,
                        sample=sample,
                        malformed_proposals=call.malformed_proposals,
                        call_record_path=call_record_path.relative_to(args.output_dir).as_posix(),
                        call_record_sha256=hashlib.sha256(
                            call_record_path.read_bytes()
                        ).hexdigest(),
                    )
                )
        record = assemble_record(
            campaign_id, observations, conditions, question=QUESTION, note=NOTE
        )
        (args.output_dir / f"{campaign_id}.convergence.json").write_text(
            record.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"[convergence] {campaign_id}: {len(record.observations)} observations, "
            f"distinct={record.distinct_execution_hashes}, converged={record.converged}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
