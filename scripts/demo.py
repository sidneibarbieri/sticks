#!/usr/bin/env python3
"""Show the central result on one campaign step, in a form a reader can follow live.

The reviewer check verifies that the artifact is intact. This shows what the artifact found: on the
same step, with the same catalog and the same declared environment, a proposer without deterministic
admission emits a step the oracle rejects, while the admitted arm refuses to emit one at all.

It reads the recorded observations, so it runs offline in a few seconds and prints the same values
the manuscript reports. Nothing is recomputed by a model here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from collect_controlled_comparison import load_campaign_fixture  # noqa: E402

COMPARISON_ROOT = PROJECT_ROOT / "release" / "experiments" / "controlled_comparison"
ARM_TITLE = {
    "prior_work_style": "Prior-work representation, no admission",
    "sticks_without_admission": "Procedural representation, no admission",
    "sticks_admitted": "Procedural representation, admission applied",
}
ARM_ORDER = ("prior_work_style", "sticks_without_admission", "sticks_admitted")
RULE = "-" * 78


def load_observations(experiment_id: str) -> list[dict]:
    cache = COMPARISON_ROOT / experiment_id / "cache"
    if not cache.is_dir():
        raise FileNotFoundError(f"no recorded run at {cache}")
    return [json.loads(path.read_text()) for path in sorted(cache.glob("*.json"))]


def choose_contrasting_step(observations: list[dict]) -> tuple[str, str, int]:
    """Pick a step where the unadmitted arms emit a rejected proposal and the admitted arm refuses."""
    rejected = {
        (item["campaign_id"], item["step_id"], item["seed"])
        for item in observations
        if item["arm_id"] == "prior_work_style" and item["emitted"] and not item["oracle_admitted"]
    }
    abstained = {
        (item["campaign_id"], item["step_id"], item["seed"])
        for item in observations
        if item["arm_id"] == "sticks_admitted" and item["abstained"]
    }
    both = sorted(rejected & abstained)
    if not both:
        raise LookupError("no step where an unadmitted arm was rejected and the admitted arm refused")
    return both[0]


def describe_step(campaign_id: str, step_id: str) -> tuple[str, list[str]]:
    fixture = load_campaign_fixture(campaign_id)
    step = next(item for item in fixture.steps if item.step_id == step_id)
    return step.technique_id, list(step.known_facts)


def arm_outcome(observations: list[dict], key: tuple[str, str, int], arm: str) -> dict:
    campaign_id, step_id, seed = key
    return next(
        item
        for item in observations
        if item["arm_id"] == arm
        and item["campaign_id"] == campaign_id
        and item["step_id"] == step_id
        and item["seed"] == seed
    )


def print_step_contrast(observations: list[dict], key: tuple[str, str, int]) -> None:
    campaign_id, step_id, seed = key
    technique_id, known_facts = describe_step(campaign_id, step_id)
    print(RULE)
    print(f"ONE STEP OF CAMPAIGN {campaign_id}   step {step_id}   technique {technique_id}   seed {seed}")
    print(RULE)
    print("Facts known to hold before this step:")
    for fact in known_facts:
        print(f"    {fact}")
    print("\nAll three arms receive the same step, the same catalog, and the same environment.")
    print("They differ only in the representation shown and whether admission is applied.\n")

    for arm in ARM_ORDER:
        outcome = arm_outcome(observations, key, arm)
        print(f"  {ARM_TITLE[arm]}")
        if outcome["abstained"]:
            print("      proposed:  a realization the verifier did not admit")
            print("      committed: nothing. The arm abstains rather than emit an unexecutable step.")
        else:
            verdict = "accepted by the oracle" if outcome["oracle_admitted"] else "REJECTED by the oracle"
            print(f"      proposed:  {outcome['template_id']}")
            print(f"      committed: this step, {verdict}")
        print()


def print_totals(experiment_id: str) -> None:
    analysis = json.loads((COMPARISON_ROOT / experiment_id / "analysis.json").read_text())
    print(RULE)
    print(f"ACROSS THE WHOLE RUN   {analysis['observations']} observations   campaigns {', '.join(analysis['campaigns'])}")
    print(RULE)
    print(f"  {'arm':<46}{'valid':>8}{'abstained':>12}")
    for row in analysis["overall"]:
        print(f"  {ARM_TITLE[row['arm']]:<46}{row['validity_rate']:>8.3f}{row['abstention_rate']:>12.3f}")
    profile = analysis["abstention_profile"]
    justified = profile["justified_no_admissible_realization"]
    print(
        f"\n  Of {profile['abstentions']} abstentions, {justified} occurred where no catalog template "
        f"was admissible at all."
    )
    print("  Refusing is the only sound answer there, and it is where the other arms emit a rejected step.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", default="2026-09-07-local")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    observations = load_observations(args.experiment_id)
    key = choose_contrasting_step(observations)
    print()
    print_step_contrast(observations, key)
    print_totals(args.experiment_id)
    print(RULE)
    print("Admission decides executable validity. The representation alone does not.")
    print(RULE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
