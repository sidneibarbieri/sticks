#!/usr/bin/env python3
"""Compute unconstrained-reconstruction divergence from the frozen raw reconstructions.

The raw reconstructions are collected once from local models (a separate, non-deterministic
step). This build is deterministic: it reads those frozen files and recomputes the divergence
metric, so the corpus record regenerates byte-identically offline and a reviewer without local
models can still verify the measurement.
"""

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

from evaluation.unconstrained_reconstruction import (  # noqa: E402
    CatalogOnlyArm,
    DeterministicControl,
    Reconstruction,
    aggregate,
    step_divergence,
)

EXPERIMENT_DIR = PROJECT_ROOT / "release" / "experiments" / "unconstrained_divergence"
RECONSTRUCTIONS_DIR = EXPERIMENT_DIR / "reconstructions"
DETERMINISTIC_DIR = EXPERIMENT_DIR / "reconstructions_deterministic"
CATALOG_ONLY_DIR = EXPERIMENT_DIR / "catalog_only"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
DEFAULT_OUTPUT = EXPERIMENT_DIR / "corpus.json"

NOTE = (
    "Three arms share the same steps and declared environment. The unconstrained arm has "
    "neither catalog nor verifier, the catalog-only arm supplies the catalog through the "
    "finite-domain prompt but applies no admission, and the finite-domain arm applies both. "
    "Comparing them separates restricting the space of realizations from deciding admission "
    "over that space. The finite-domain arm's convergence is not evidence that sampling was "
    "eliminated, since that arm collapses any proposal set by construction; the "
    "temperature-0 control tests that separately. Proposers often agree on what to do while "
    "committing different concrete tools, sources, targets, and parameters."
)


def _deterministic_control() -> DeterministicControl | None:
    """Cross-proposer divergence and per-proposer reproducibility with sampling disabled."""
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(DETERMINISTIC_DIR.glob("*.json"))
    ]
    if not records:
        return None

    # Reproducibility compares repeated samples of the same campaign by the same proposer;
    # grouping by proposer alone would compare different campaigns and always differ.
    repeated: dict[tuple[str, str], list[str]] = {}
    for record in records:
        key = (record["model"], record["campaign_id"])
        repeated.setdefault(key, []).append(
            json.dumps(record["realizations"], sort_keys=True)
        )
    reproducible = {
        model: len(set(outputs)) == 1
        for (model, _campaign), outputs in repeated.items()
        if len(outputs) > 1
    }

    steps = _group(records, first_sample_only=True)
    per_step = [step_divergence(reconstructions) for reconstructions in steps.values()]
    step_count = len(per_step)
    return DeterministicControl(
        proposers_per_step=max(step.reconstruction_count for step in per_step),
        mean_distinct_procedures=sum(
            step.distinct_executable_decisions for step in per_step
        )
        / step_count,
        steps_with_full_agreement=sum(
            1 for step in per_step if step.distinct_executable_decisions == 1
        ),
        pairwise_agreement_rate=sum(step.decision_agreement_rate for step in per_step)
        / step_count,
        within_proposer_reproducible=reproducible,
    )


def _catalog_only_arm() -> CatalogOnlyArm | None:
    """Divergence over proposals made against the catalog, with no admission applied."""
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CATALOG_ONLY_DIR.glob("*.json"))
    ]
    if not records:
        return None

    known_templates = {
        template["template_id"]
        for template in json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    }
    steps: dict[str, list[Reconstruction]] = {}
    outside_catalog = 0
    for record in records:
        proposer = f"{record['model']}.{record['sample']}"
        for proposal in record["proposals"]:
            if proposal["template_id"] not in known_templates:
                outside_catalog += 1
            key = f"{record['campaign_id']}:{proposal['technique_id']}"
            steps.setdefault(key, []).append(
                Reconstruction(
                    technique_id=str(proposal["technique_id"]),
                    proposer=proposer,
                    # The realization a proposer commits here is the template it names plus
                    # the bindings it assigns, which is the finite-domain arm's decision unit.
                    mechanism=str(proposal["template_id"]),
                    target="",
                    command="",
                    parameters={
                        str(name): str(value)
                        for name, value in (proposal.get("bindings") or {}).items()
                    },
                )
            )
    per_step = [step_divergence(group) for group in steps.values()]
    step_count = len(per_step)
    return CatalogOnlyArm(
        steps=step_count,
        proposers_per_step=max(step.reconstruction_count for step in per_step),
        mean_distinct_realizations=sum(
            step.distinct_executable_decisions for step in per_step
        )
        / step_count,
        steps_with_full_agreement=sum(
            1 for step in per_step if step.distinct_executable_decisions == 1
        ),
        pairwise_agreement_rate=sum(step.decision_agreement_rate for step in per_step)
        / step_count,
        proposals_outside_catalog=outside_catalog,
        malformed_proposals=sum(record["malformed_proposals"] for record in records),
    )


def _group(records: list[dict], *, first_sample_only: bool = False) -> dict[str, list[Reconstruction]]:
    """Group reconstructions by campaign-scoped technique step."""
    steps: dict[str, list[Reconstruction]] = {}
    for record in records:
        if first_sample_only and record["sample"] != 1:
            continue
        proposer = f"{record['model']}.{record['sample']}"
        for realization in record["realizations"]:
            technique_id = str(realization.get("technique_id", ""))
            key = f"{record['campaign_id']}:{technique_id}"
            parameters = realization.get("parameters") or {}
            steps.setdefault(key, []).append(
                Reconstruction(
                    technique_id=technique_id,
                    proposer=proposer,
                    mechanism=str(realization.get("mechanism", "")),
                    target=str(realization.get("target", "")),
                    command=str(realization.get("command", "")),
                    parameters={str(name): str(value) for name, value in parameters.items()},
                )
            )
    return steps


def _load_reconstructions() -> dict[str, list[Reconstruction]]:
    """Group every frozen reconstruction by its campaign-scoped technique step."""
    steps: dict[str, list[Reconstruction]] = {}
    for path in sorted(RECONSTRUCTIONS_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        proposer = f"{record['model']}.{record['sample']}"
        for realization in record["realizations"]:
            technique_id = str(realization.get("technique_id", ""))
            key = f"{record['campaign_id']}:{technique_id}"
            parameters = realization.get("parameters") or {}
            steps.setdefault(key, []).append(
                Reconstruction(
                    technique_id=technique_id,
                    proposer=proposer,
                    mechanism=str(realization.get("mechanism", "")),
                    target=str(realization.get("target", "")),
                    command=str(realization.get("command", "")),
                    parameters={str(name): str(value) for name, value in parameters.items()},
                )
            )
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    steps = _load_reconstructions()
    if not steps:
        raise FileNotFoundError(f"no frozen reconstructions under {RECONSTRUCTIONS_DIR}")
    campaigns = len({key.split(":", 1)[0] for key in steps})
    per_step = [step_divergence(reconstructions) for reconstructions in steps.values()]
    corpus = aggregate(per_step, note=NOTE, campaigns=campaigns)
    corpus.deterministic_control = _deterministic_control()
    corpus.catalog_only_arm = _catalog_only_arm()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(corpus.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        f"[unconstrained-divergence] {corpus.steps} steps, {corpus.proposers_per_step} "
        f"proposers/step: mean {corpus.mean_distinct_executable_decisions:.2f} distinct "
        f"executable decisions, {corpus.mean_decision_agreement_rate * 100:.1f}% pairwise "
        f"agreement, {corpus.steps_with_full_decision_agreement}/{corpus.steps} steps converge"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
