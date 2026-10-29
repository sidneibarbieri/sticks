#!/usr/bin/env python3
"""Extend catalog coverage by bounded LLM proposal and deterministic admission (Stage 2).

Catalog authoring is the manual step this project otherwise leaves to a person. Here an
untrusted model proposes a typed template for each uncovered technique, and a deterministic
gate admits it only when it is well-formed over the catalog's declared vocabularies. The model
never promotes its own template: an admitted one is a DRAFT with proposer provenance, and the
trusted catalog the paper's frozen numbers rest on is left untouched.

Each invocation is one isolated run under release/experiments/stage2_authoring/runs/<run-id>.
The frozen run (calls/, proposed_templates/, generation_summary.json) is read to know what is
already covered and is never written. Techniques are attempted in order of how many corpus
steps they cover. The lift is reported as contract-valid reach, a weaker tier than
admitted-and-executed, and is labelled as such.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from evaluation.technique_coverage import coverage_extension  # noqa: E402
from concretization.evidence_policy import load_roles  # noqa: E402
from concretization.provider import (  # noqa: E402
    BudgetLedger,
    ProviderKind,
    complete_raw,
    load_config,
    require_credential,
)
from curation.authoring_run import (  # noqa: E402
    AuthoringRun,
    FrozenBaseline,
    OutcomeStatus,
    ProposerSettings,
    RunManifest,
    TechniqueDecision,
    source_revision,
    utc_timestamp,
)
from curation.template_author import (  # noqa: E402
    AdmissionVocabulary,
    TemplateProposalOutcome,
    admit_response,
)

BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"
CATALOG = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
ROLES = PROJECT_ROOT / "data" / "concretization" / "evidence_predicate_roles.json"
PLANS = PROJECT_ROOT / "release" / "plans" / "enterprise"
FROZEN_DRAFTS = PROJECT_ROOT / "data" / "concretization" / "proposed_templates"
RUNS_ROOT = PROJECT_ROOT / "release" / "experiments" / "stage2_authoring" / "runs"

SYSTEM_PROMPT = (
    "You author one procedure template for a MITRE ATT&CK technique, for a benign laboratory "
    "harness. Reply with a single JSON object and nothing else, with keys: template_id "
    "(kebab-case, unique, descriptive), technique_ids (a list holding exactly the requested "
    "technique id), execution_domain (one of attacker, boundary, target), parameter_kinds (an "
    "object mapping a short parameter name to a binding kind chosen ONLY from the allowed "
    "kinds), requires (list of fact strings the step needs), produces (non-empty list of fact "
    "strings the step establishes), evidence_predicates (non-empty list chosen ONLY from the "
    "allowed predicates, including at least one effect predicate), fidelity_ceiling (adapted or "
    "inspired; never faithful), and description (one sentence). Choose an effect predicate that "
    "observes a state the step produces. Never invent a predicate or binding kind."
)


def bindable_kinds() -> frozenset[str]:
    kinds: set[str] = set()
    for path in PLANS.glob("*.binding-catalog.json"):
        for binding in json.loads(path.read_text(encoding="utf-8")).get("bindings", []):
            kinds.add(binding["kind"])
    for path in (PROJECT_ROOT / "release" / "plans").glob("C00*.binding-catalog.json"):
        for binding in json.loads(path.read_text(encoding="utf-8")).get("bindings", []):
            kinds.add(binding["kind"])
    return frozenset(kinds)


def technique_reference() -> dict[str, dict[str, str]]:
    """Map each ATT&CK technique id to its name and description, for grounding the proposer."""
    reference: dict[str, dict[str, str]] = {}
    for obj in json.loads(BUNDLE.read_text(encoding="utf-8"))["objects"]:
        if obj.get("type") != "attack-pattern":
            continue
        for external in obj.get("external_references", []):
            if external.get("source_name") == "mitre-attack":
                reference[external.get("external_id", "")] = {
                    "name": obj.get("name", ""),
                    "description": obj.get("description", "")[:600],
                }
    return reference


def step_counts() -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in PLANS.glob("*.procedural-plan.json"):
        for step in json.loads(path.read_text(encoding="utf-8"))["steps"]:
            counts[step["technique_id"]] += 1
    return counts


def trusted_techniques() -> set[str]:
    return {
        technique
        for template in json.loads(CATALOG.read_text(encoding="utf-8"))["templates"]
        for technique in template["technique_ids"]
    }


def frozen_draft_techniques() -> set[str]:
    return {
        technique
        for path in FROZEN_DRAFTS.glob("*.json")
        for technique in json.loads(path.read_text(encoding="utf-8"))["template"]["technique_ids"]
    }


def uncovered_by_coverage(already_drafted: frozenset[str] = frozenset()) -> list[tuple[str, int]]:
    """Techniques neither trusted nor already drafted, most-covering first."""
    covered = trusted_techniques() | already_drafted
    uncovered = {
        technique: count for technique, count in step_counts().items() if technique not in covered
    }
    return sorted(uncovered.items(), key=lambda item: (-item[1], item[0]))


def select_targets(
    uncovered: list[tuple[str, int]], requested_techniques: list[str], limit: int
) -> list[tuple[str, int]]:
    """Select an explicit corpus subset without silently widening provider calls."""
    if not requested_techniques:
        return uncovered[:limit]
    counts = dict(uncovered)
    unknown = sorted(set(requested_techniques) - set(counts))
    if unknown:
        raise ValueError(
            "requested techniques are already covered or absent from the corpus: "
            + ", ".join(unknown)
        )
    return [(technique_id, counts[technique_id]) for technique_id in requested_techniques]


def author_one(
    technique_id, call_dir, reference, config, budget, vocabulary, allowed_kinds
) -> TemplateProposalOutcome:
    if call_dir.exists():
        raise FileExistsError(f"Preserved provider evidence already exists: {call_dir}")
    detail = reference.get(technique_id, {"name": technique_id, "description": ""})
    user_prompt = (
        f"Technique id: {technique_id}\nName: {detail['name']}\n"
        f"Description: {detail['description']}\n\n"
        f"Allowed binding kinds: {sorted(allowed_kinds)}\n"
        f"Allowed evidence predicates: {sorted(vocabulary.predicate_roles)}\n"
        f"Effect predicates (choose at least one): {sorted(vocabulary.effect_predicates)}"
    )
    content, _ = complete_raw(
        config,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        output_dir=call_dir,
        budget=budget,
    )
    return admit_response(technique_id, content, vocabulary)


def proposer_settings(config) -> ProposerSettings:
    return ProposerSettings(
        provider=config.provider.value,
        model=config.model,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
        timeout_seconds=config.timeout_seconds,
        max_requests=config.budget.max_requests,
        max_estimated_usd=config.budget.max_estimated_usd,
    )


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", required=True, help="Name of the new run directory.")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument(
        "--technique",
        action="append",
        default=[],
        dest="techniques",
        help="One uncovered corpus technique to author; repeat for an explicit batch.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    config = load_config(args.config)
    if config.provider != ProviderKind.replay:
        require_credential(config)
    budget = BudgetLedger(config.budget)
    allowed_kinds = bindable_kinds()
    vocabulary = AdmissionVocabulary(predicate_roles=load_roles(ROLES), bindable_kinds=allowed_kinds)
    reference = technique_reference()

    counts = step_counts()
    trusted = trusted_techniques()
    frozen_drafts = frozenset(frozen_draft_techniques())
    baseline = coverage_extension(counts, trusted, set(frozen_drafts))
    targets = select_targets(uncovered_by_coverage(frozen_drafts), args.techniques, args.limit)

    commit, dirty = source_revision(PROJECT_ROOT)
    run = AuthoringRun(RUNS_ROOT, args.run_id)
    run.create(
        RunManifest(
            run_id=args.run_id,
            started_at=utc_timestamp(),
            source_commit=commit,
            source_tree_dirty=dirty,
            proposer=proposer_settings(config),
            baseline=FrozenBaseline(
                trusted_techniques=len(trusted),
                frozen_draft_techniques=len(frozen_drafts),
                frozen_reach_steps=baseline["extended_contract_reach_steps"],
                total_steps=baseline["total_steps"],
            ),
            target_techniques=[technique for technique, _ in targets],
        )
    )

    admitted: set[str] = set()
    rejected: Counter[str] = Counter()
    provider_failures = 0
    for technique_id, corpus_steps in targets:
        call_dir = run.calls / technique_id.replace(".", "_")
        try:
            outcome = author_one(
                technique_id, call_dir, reference, config, budget, vocabulary, allowed_kinds
            )
        except (TimeoutError, OSError) as failure:
            # A transient provider or network fault is recorded so one bad call does not
            # discard a long batch. A budget or programming error still propagates.
            provider_failures += 1
            run.record(TechniqueDecision(
                technique_id=technique_id, corpus_steps=corpus_steps,
                status=OutcomeStatus.provider_failure, detail=type(failure).__name__,
            ))
            continue
        if outcome.admitted and outcome.template is not None:
            admitted.add(technique_id)
            run.write_draft(technique_id, {
                "lifecycle": "draft",
                "provenance": {
                    "source": "llm_proposer",
                    "provider": config.provider.value,
                    "model": config.model,
                    "run_id": args.run_id,
                    "review_pending": True,
                },
                "template": outcome.template.model_dump(),
            })
            run.record(TechniqueDecision(
                technique_id=technique_id, corpus_steps=corpus_steps, status=OutcomeStatus.admitted,
            ))
        else:
            code = outcome.rejection_code.value if outcome.rejection_code else "unknown"
            rejected[code] += 1
            run.record(TechniqueDecision(
                technique_id=technique_id, corpus_steps=corpus_steps, status=OutcomeStatus.rejected,
                rejection_code=code, detail=outcome.rejection_detail[:500],
            ))

    combined = coverage_extension(counts, trusted, set(frozen_drafts) | admitted)
    run.write_summary({
        "run_id": args.run_id,
        "attempted_techniques": len(targets),
        "admitted_templates": len(admitted),
        "rejected_by_code": dict(sorted(rejected.items())),
        "provider_failures": provider_failures,
        "frozen_reach_steps": baseline["extended_contract_reach_steps"],
        "combined_reach_steps": combined["extended_contract_reach_steps"],
        "run_increment_steps": (
            combined["extended_contract_reach_steps"] - baseline["extended_contract_reach_steps"]
        ),
        "total_steps": combined["total_steps"],
        "matching_policy": "exact_technique_id",
        "evidence_tier": "schema_and_vocabulary_valid_draft",
        "budget_requests_used": budget.requests,
        "budget_estimated_usd": round(budget.estimated_usd, 4),
        "note": (
            "Drafts of this run are untrusted, review-pending, and separate from the frozen run. "
            "Combined reach is contract-valid reach, not admitted-and-executed coverage."
        ),
    })
    print(f"[stage2:{args.run_id}] attempted {len(targets)}, admitted {len(admitted)}, "
          f"reach {baseline['extended_contract_reach_steps']} -> "
          f"{combined['extended_contract_reach_steps']}/{combined['total_steps']}, "
          f"${budget.estimated_usd:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
