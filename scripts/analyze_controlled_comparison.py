#!/usr/bin/env python3
"""Analyze a collected controlled comparison into the reported table.

Reads the frozen per-cell observations, joins each step to its technique through the same fixture
loader the collection used, and reports per-arm validity, abstention, and divergence with a
bootstrap confidence interval clustered by campaign and step. Clustering matters because the seeds
of one step are correlated; resampling cells instead of steps would report intervals that are too
tight.

The analysis never re-runs the model: it is a pure function of the cached observations, so the
reported numbers regenerate byte-for-byte. Invalid parsed proposals and malformed model replies
both count against proposal validity; explicit abstentions have a separate denominator.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from audit_prospective_collection import audit_collection  # noqa: E402
from collect_controlled_comparison import load_campaign_fixture  # noqa: E402
from concretization.models import BindingScope, ProcedureProposal  # noqa: E402
from concretization.verifier import assess_candidate  # noqa: E402
from evaluation.controlled_comparison import ArmId  # noqa: E402

ARMS = (ArmId.prior_work_style, ArmId.sticks_without_admission, ArmId.sticks_admitted)
BOOTSTRAP_RESAMPLES = 2000


def load_observations(experiment_dir: Path) -> list[dict]:
    cache_dir = experiment_dir / "cache"
    return [json.loads(path.read_text()) for path in sorted(cache_dir.glob("*.json"))]


def technique_index(campaigns: list[str]) -> dict[tuple[str, str], str]:
    index: dict[tuple[str, str], str] = {}
    for campaign in campaigns:
        for step in load_campaign_fixture(campaign).steps:
            index[(campaign, step.step_id)] = step.technique_id
    return index


def _validity(observations: list[dict], arm: str) -> float | None:
    attempts = [
        item for item in observations
        if item["arm_id"] == arm and (item["emitted"] or item.get("parse_error") is not None)
    ]
    if not attempts:
        return None
    return sum(bool(item.get("oracle_admitted")) for item in attempts) / len(attempts)


def arm_summary(observations: list[dict], arm: str) -> dict[str, object]:
    rows = [item for item in observations if item["arm_id"] == arm]
    emitted = [item for item in rows if item["emitted"]]
    abstained = [item for item in rows if item["abstained"]]
    templates_by_step: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    for item in emitted:
        if item["template_id"] is not None:
            templates_by_step[(item["campaign_id"], item["step_id"])].add(item["template_id"])
    distinct = [len(values) for values in templates_by_step.values()]
    return {
        "arm": arm,
        "steps": len(rows),
        "emitted": len(emitted),
        "valid": sum(bool(item.get("oracle_admitted")) for item in emitted),
        "abstained": len(abstained),
        "validity_rate": _validity(rows, arm) or 0.0,
        "abstention_rate": len(abstained) / len(rows) if rows else 0.0,
        "mean_distinct_templates_per_step": sum(distinct) / len(distinct) if distinct else 0.0,
    }


def clustered_bootstrap(
    observations: list[dict], arm: str, reference_arm: str, seed: int
) -> dict[str, float]:
    """Resample whole (campaign, step) clusters, not individual cells."""
    clusters: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for item in observations:
        clusters[(item["campaign_id"], item["step_id"])].append(item)
    keys = list(clusters)
    generator = random.Random(seed)
    gaps: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = [item for _ in keys for item in clusters[keys[generator.randrange(len(keys))]]]
        treated, reference = _validity(sample, arm), _validity(sample, reference_arm)
        if treated is not None and reference is not None:
            gaps.append(treated - reference)
    gaps.sort()
    return {
        "mean_gap": sum(gaps) / len(gaps),
        "ci_low": gaps[int(0.025 * len(gaps))],
        "ci_high": gaps[int(0.975 * len(gaps))],
        "resamples": len(gaps),
    }


def failure_profile(observations: list[dict], index: dict[tuple[str, str], str]) -> dict[str, dict]:
    invalid = collections.Counter(
        index[(item["campaign_id"], item["step_id"])]
        for item in observations
        if item["arm_id"] == ArmId.prior_work_style.value
        and (item["emitted"] or item.get("parse_error") is not None)
        and not item.get("oracle_admitted")
    )
    abstained = collections.Counter(
        index[(item["campaign_id"], item["step_id"])]
        for item in observations
        if item["arm_id"] == ArmId.sticks_admitted.value and item["abstained"]
    )
    return {
        "prior_work_invalid_by_technique": dict(sorted(invalid.items())),
        "admitted_abstained_by_technique": dict(sorted(abstained.items())),
    }


def abstention_profile(observations: list[dict], campaigns: list[str]) -> dict[str, object]:
    """Split abstentions into justified and recoverable.

    An abstention is justified when no catalog template is admissible at that step's fact-state:
    refusing is then the only sound answer, and it is exactly where an unadmitted arm must emit
    something invalid. An abstention is recoverable when an admissible template did exist and the
    proposer's single attempt missed it. This establishes catalog feasibility under the same
    admission predicate; it does not show that a retry would find the template or produce an
    observed effect in a SUT.
    """
    fixtures = {campaign: load_campaign_fixture(campaign) for campaign in campaigns}
    verdicts: dict[tuple[str, str], bool] = {}
    for campaign, fixture in fixtures.items():
        catalog_by_id = {template.template_id: template for template in fixture.templates}
        for step in fixture.steps:
            admissible = False
            for template_id, template in catalog_by_id.items():
                bindings = {}
                for parameter, kind in template.parameter_kinds.items():
                    matching = [
                        binding.binding_id
                        for binding in fixture.catalog.bindings
                        if binding.kind == kind and binding.scope == BindingScope.lab
                    ]
                    if matching:
                        bindings[parameter] = matching[0]
                proposal = ProcedureProposal(
                    technique_id=step.technique_id,
                    template_id=template_id,
                    bindings=bindings,
                    source="abstention_audit",
                )
                assessment = assess_candidate(
                    proposal,
                    technique_id=step.technique_id,
                    execution_domain=step.execution_domain,
                    templates=catalog_by_id,
                    catalog=fixture.catalog,
                    known_facts=set(step.known_facts),
                )
                if assessment.accepted:
                    admissible = True
                    break
            verdicts[(campaign, step.step_id)] = admissible

    justified = recoverable = 0
    for item in observations:
        if item["arm_id"] != ArmId.sticks_admitted.value or not item["abstained"]:
            continue
        if verdicts[(item["campaign_id"], item["step_id"])]:
            recoverable += 1
        else:
            justified += 1
    total = justified + recoverable
    return {
        "abstentions": total,
        "justified_no_admissible_realization": justified,
        "recoverable_proposer_miss": recoverable,
        "justified_share": justified / total if total else 0.0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", default="2026-09-07-local")
    parser.add_argument("--bootstrap-seed", type=int, default=20260907)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    experiment_dir = (
        PROJECT_ROOT / "release" / "experiments" / "controlled_comparison" / args.experiment_id
    )
    audit_collection(args.experiment_id)
    observations = load_observations(experiment_dir)
    campaigns = sorted({item["campaign_id"] for item in observations})
    index = technique_index(campaigns)

    overall = [arm_summary(observations, arm.value) for arm in ARMS]
    per_campaign = {
        campaign: [
            arm_summary([o for o in observations if o["campaign_id"] == campaign], arm.value)
            for arm in ARMS
        ]
        for campaign in campaigns
    }
    gaps = {
        arm.value: clustered_bootstrap(
            observations, ArmId.sticks_admitted.value, arm.value, args.bootstrap_seed
        )
        for arm in (ArmId.prior_work_style, ArmId.sticks_without_admission)
    }
    report = {
        "experiment_id": args.experiment_id,
        "observations": len(observations),
        "campaigns": campaigns,
        "overall": overall,
        "per_campaign": per_campaign,
        "validity_gap_vs_admitted": gaps,
        "failure_profile": failure_profile(observations, index),
        "abstention_profile": abstention_profile(observations, campaigns),
    }
    (experiment_dir / "analysis.json").write_text(json.dumps(report, indent=2) + "\n")

    print(f"observations={len(observations)} campaigns={campaigns}\n")
    for row in overall:
        print(
            f"{row['arm']:26} emitted={row['emitted']:3} valid={row['valid']:3} "
            f"abstained={row['abstained']:2} validity={row['validity_rate']:.3f} "
            f"abstention={row['abstention_rate']:.3f} divergence={row['mean_distinct_templates_per_step']:.3f}"
        )
    print("\nvalidity gap of sticks_admitted over:")
    for arm, gap in gaps.items():
        print(f"  {arm:26} +{gap['mean_gap']:.3f}  95% CI [{gap['ci_low']:.3f}, {gap['ci_high']:.3f}]")
    profile = report["abstention_profile"]
    print(
        f"\nabstentions={profile['abstentions']} "
        f"justified={profile['justified_no_admissible_realization']} "
        f"recoverable={profile['recoverable_proposer_miss']} "
        f"justified_share={profile['justified_share']:.3f}"
    )
    print(f"\nwrote {experiment_dir / 'analysis.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
