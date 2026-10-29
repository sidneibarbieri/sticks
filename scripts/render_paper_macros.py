#!/usr/bin/env python3
"""Render LaTeX macros for the manuscript from the frozen evidence records.

Every number the manuscript reports is defined here and read from a frozen record, so no
value is transcribed by hand. Writing the macro file into the artifact keeps the paper a
consumer of evidence: the manuscript inputs the generated file and never computes.

Fails loud if a record is missing or a total disagrees with its parts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = PROJECT_ROOT / "release" / "experiments"
PAPER_AUTHORING_RUNS = tuple(
    json.loads((EXPERIMENTS / "stage2_authoring" / "paper_runs.json").read_text(encoding="utf-8"))["run_ids"]
)
DEFAULT_OUTPUT = PROJECT_ROOT / "release" / "paper_macros.tex"
DEEP_CAMPAIGNS = ("C0010", "C0026", "C0045")
ENTERPRISE_BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"
SOLVER_PROPOSER = "finite_domain_solver"


def _load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"missing frozen evidence record: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline_totals() -> dict[str, int]:
    records = [
        _load(EXPERIMENTS / "enrichment_baseline" / f"{campaign}.baseline.json")
        for campaign in DEEP_CAMPAIGNS
    ]
    return {
        "steps": sum(record["total_steps"] for record in records),
        "raw": sum(record["raw_stix_executable_steps"] for record in records),
        "enriched": sum(record["enriched_executable_steps"] for record in records),
    }


def _commitment_totals() -> dict[str, int]:
    records = [
        _load(EXPERIMENTS / "execution_commitments" / f"{campaign}.commitments.json")
        for campaign in DEEP_CAMPAIGNS
    ]
    totals = {
        "mechanism": sum(record["mechanism_commitments"] for record in records),
        "binding": sum(record["binding_commitments"] for record in records),
        "total": sum(record["total_execution_commitments"] for record in records),
    }
    if totals["mechanism"] + totals["binding"] != totals["total"]:
        raise ValueError("commitment totals disagree with their parts")
    return totals


def _provenance_totals() -> dict[str, float | int]:
    records = [
        _load(EXPERIMENTS / "provenance" / f"{campaign}.provenance.json")
        for campaign in DEEP_CAMPAIGNS
    ]
    counts = {"cti_evidenced": 0, "environment_determined": 0, "system_introduced": 0}
    occurrences = 0
    for record in records:
        occurrences += record["total_binding_occurrences"]
        for key in counts:
            counts[key] += record["binding_occurrence_counts"][key]
    if sum(counts.values()) != occurrences:
        raise ValueError("provenance class counts disagree with the occurrence total")
    environment_rates = [
        record["binding_occurrence_counts"]["environment_determined"]
        / record["total_binding_occurrences"]
        for record in records
    ]
    return {
        **counts,
        "occurrences": occurrences,
        "environment_rate_min": min(environment_rates),
        "environment_rate_max": max(environment_rates),
    }


def _attack_version() -> str:
    bundle = _load(ENTERPRISE_BUNDLE)
    versions = {
        item["x_mitre_version"]
        for item in bundle["objects"]
        if item.get("type") == "x-mitre-collection"
        and item.get("name") == "Enterprise ATT&CK"
    }
    if len(versions) != 1:
        raise ValueError(f"expected one Enterprise ATT&CK version, found {versions}")
    return versions.pop()


def _active_campaign_count() -> int:
    """Active Enterprise campaigns in the pinned bundle, whether or not they reach a technique."""
    bundle = _load(ENTERPRISE_BUNDLE)
    identifiers = {
        reference["external_id"]
        for item in bundle["objects"]
        if item.get("type") == "campaign"
        and not item.get("revoked")
        and not item.get("x_mitre_deprecated")
        for reference in item.get("external_references", [])
        if reference.get("source_name") == "mitre-attack"
    }
    return len(identifiers)


def _convergence_totals() -> dict[str, int]:
    records = [
        _load(EXPERIMENTS / "proposer_convergence" / f"{campaign}.convergence.json")
        for campaign in DEEP_CAMPAIGNS
    ]
    distinct = {
        observation["execution_semantic_sha256"]
        for record in records
        for observation in record["observations"]
    }
    if any(not record["converged"] for record in records):
        raise ValueError("a campaign did not converge across proposers")
    model_observations = [
        observation
        for record in records
        for observation in record["observations"]
        if observation["proposer"] != SOLVER_PROPOSER
    ]
    return {
        "observations": sum(len(record["observations"]) for record in records),
        "distinct_per_campaign": max(record["distinct_execution_hashes"] for record in records),
        "campaigns": len(records),
        "distinct_overall": len(distinct),
        "model_observations": len(model_observations),
        "proposer_contributing": sum(
            1
            for observation in model_observations
            if observation["committed_from_proposer"] > 0
        ),
    }


def _behavioral_structure() -> dict:
    return _load(EXPERIMENTS / "behavioral_structure" / "corpus.json")


def _corpus_characterization() -> dict:
    return _load(EXPERIMENTS / "corpus_characterization" / "corpus.json")


def _derived_environment_totals() -> dict[str, int]:
    record = _load(EXPERIMENTS / "derived_environment" / "corpus.json")
    return {
        "campaigns": record["campaigns"],
        "admitted": record["admitted_steps"],
        "with_admitted_step": record["campaigns"] - record["campaigns_with_no_admitted_step"],
    }


def _divergence_totals() -> dict[str, str]:
    record = _load(EXPERIMENTS / "unconstrained_divergence" / "corpus.json")
    control = record["deterministic_control"]
    reproducible = control["within_proposer_reproducible"]
    catalog_only = record.get("catalog_only_arm") or {}
    return {
        "catalog_only_distinct": f"{catalog_only.get('mean_distinct_realizations', 0):.1f}",
        "catalog_only_agreement": f"{catalog_only.get('pairwise_agreement_rate', 0) * 100:.1f}",
        "catalog_only_converged": str(catalog_only.get("steps_with_full_agreement", 0)),
        "catalog_only_outside": str(catalog_only.get("proposals_outside_catalog", 0)),
        "det_proposers": str(control["proposers_per_step"]),
        "det_distinct": f"{control['mean_distinct_procedures']:.1f}",
        "det_converged": str(control["steps_with_full_agreement"]),
        "det_reproducible": str(sum(1 for value in reproducible.values() if value)),
        "det_repeated": str(len(reproducible)),
        "steps": str(record["steps"]),
        "proposers": str(record["proposers_per_step"]),
        "distinct_decisions": f"{record['mean_distinct_executable_decisions']:.1f}",
        "agreement_pct": f"{record['mean_decision_agreement_rate'] * 100:.1f}",
        "converged_steps": str(record["steps_with_full_decision_agreement"]),
    }


def _evidence_policy() -> dict[str, int]:
    report = _load(EXPERIMENTS / "evidence_policy" / "catalog.json")
    return {
        "templates": report["template_count"],
        "effect_certified": report["effect_certified_count"],
        "registered": report["registered_predicate_count"],
        "effect_names": report["role_counts"]["effect"],
        "safety_names": report["role_counts"]["safety"],
    }


def _authoring_cost() -> dict[str, str]:
    summary = _load(EXPERIMENTS / "authoring_cost" / "corpus.json")["summary"]
    automation = summary["automation"]
    return {
        "templates": str(summary["templates"]),
        "fields": str(summary["total_fields"]),
        "median": str(summary["median_fields"]),
        "max": str(summary["max_fields"]),
        "steps": str(summary["covered_steps"]),
        "reuse": f"{summary['steps_per_template']:.1f}",
        "proposals": str(automation["proposals"]),
        "admitted": str(automation["admitted"]),
        "rejected": str(automation["rejected"]),
        "admitted_pct": f"{100 * automation['admitted'] / automation['proposals']:.1f}",
    }


def _isolated_authoring_runs() -> dict[str, str]:
    """Read only the runs explicitly selected for the manuscript."""
    run_root = EXPERIMENTS / "stage2_authoring" / "runs"
    summaries = [_load(run_root / run_id / "summary.json") for run_id in PAPER_AUTHORING_RUNS]
    decisions = []
    for run_id, summary in zip(PAPER_AUTHORING_RUNS, summaries, strict=True):
        if summary["run_id"] != run_id:
            raise ValueError(f"authoring run identity mismatch: {run_id}")
        path = run_root / run_id / "decisions.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        verdicts = {
            row["technique_id"]: (row["status"], row["rejection_code"])
            for row in rows
        }
        if len(verdicts) != len(rows) or len(rows) != summary["attempted_techniques"]:
            raise ValueError(f"authoring decision count mismatch: {run_id}")
        if sum(status == "admitted" for status, _ in verdicts.values()) != summary["admitted_templates"]:
            raise ValueError(f"authoring admission count mismatch: {run_id}")
        decisions.append(verdicts)
    if decisions[0] != decisions[1]:
        raise ValueError("isolated authoring runs disagree on decisions")
    compared_fields = ("attempted_techniques", "admitted_templates", "combined_reach_steps", "total_steps")
    if any(summary[field] != summaries[0][field] for summary in summaries for field in compared_fields):
        raise ValueError("isolated authoring run summaries disagree")
    first = summaries[0]
    return {
        "runs": str(len(summaries)),
        "attempted": str(first["attempted_techniques"]),
        "admitted": str(first["admitted_templates"]),
        "reach": str(first["combined_reach_steps"]),
        "share": f"{100 * first['combined_reach_steps'] / first['total_steps']:.1f}",
    }


def _enumeration_scaling() -> dict[str, str]:
    report = _load(EXPERIMENTS / "enumeration_scaling" / "corpus.json")
    return {
        "grid_points": str(report["grid_points"]),
        "largest_set": str(report["largest_candidate_set"]),
        "refused_size": str(report["refusal_probe"]["predicted_candidates"]),
        "default_ceiling": str(report["default_ceiling"]),
    }


def _attack_flow_interop() -> dict[str, str]:
    report = _load(EXPERIMENTS / "attack_flow_interop" / "flow.json")
    return {
        "actions": str(report["actions_with_technique"]),
        "edges": str(report["declared_action_edges"]),
        "inversions": str(report["order_inversions"]),
        "pairs": str(report["order_pairs"]),
        "covered": str(report["catalog_supported_techniques"]),
    }


def _execution_locus() -> dict[str, str]:
    report = _load(EXPERIMENTS / "execution_locus" / "corpus.json")
    steps = report["steps_by_domain"]
    templates = report["templates_by_domain"]
    return {
        "target_steps": str(steps["target"]),
        "boundary_steps": str(steps["boundary"]),
        "attacker_steps": str(steps["attacker"]),
        "target_share": f"{report['step_share_by_domain']['target'] * 100:.1f}",
        "target_templates": str(templates["target"]),
        "boundary_templates": str(templates["boundary"]),
        "attacker_templates": str(templates["attacker"]),
    }


def _catalog_baseline() -> dict[str, str]:
    report = _load(EXPERIMENTS / "catalog_baseline" / "corpus.json")
    return {
        "our_reach": str(report["our_reach_steps"]),
        "baseline_reach": str(report["baseline_reach_steps"]),
        "baseline_techniques": str(report["baseline_techniques"]),
        "uncovered": str(report["baseline_uncovered_steps"]),
        "baseline_share": f"{report['baseline_reach_share'] * 100:.1f}",
    }


def _stage2_authoring() -> dict[str, str]:
    report = _load(EXPERIMENTS / "stage2_authoring" / "corpus.json")
    return {
        "proposals": str(report["proposals"]),
        "admitted": str(report["admitted_templates"]),
        "rejected": str(sum(report["rejected_by_code"].values())),
        "trusted_reach": str(report["trusted_contract_reach_steps"]),
        "extended_reach": str(report["extended_contract_reach_steps"]),
        "extended_share": f"{report['extended_contract_reach_share'] * 100:.1f}",
    }


def _percent(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator * 100:.0f}"


def build_macros() -> dict[str, str]:
    baseline = _baseline_totals()
    commitments = _commitment_totals()
    provenance = _provenance_totals()
    corpus = _load(EXPERIMENTS / "substitution" / "corpus.json")
    evidence_policy = _evidence_policy()
    scaling = _enumeration_scaling()
    flow = _attack_flow_interop()
    locus = _execution_locus()
    catalog_baseline = _catalog_baseline()
    stage2 = _stage2_authoring()
    authoring = _authoring_cost()
    isolated = _isolated_authoring_runs()
    substitution = _load(EXPERIMENTS / "behavioral_substitution" / "T1105.substitution.json")

    return {
        "attackVersion": _attack_version(),
        "authoringTemplateCount": authoring["templates"],
        "authoringFieldCount": authoring["fields"],
        "authoringMedianFields": authoring["median"],
        "authoringMaxFields": authoring["max"],
        "authoringCoveredSteps": authoring["steps"],
        "authoringStepsPerTemplate": authoring["reuse"],
        "authoringProposals": authoring["proposals"],
        "authoringAdmitted": authoring["admitted"],
        "authoringRejected": authoring["rejected"],
        "authoringAdmittedPct": authoring["admitted_pct"],
        "isolatedRunCount": isolated["runs"],
        "isolatedRunAttempted": isolated["attempted"],
        "isolatedRunAdmitted": isolated["admitted"],
        "isolatedRunReach": isolated["reach"],
        "isolatedRunReachShare": isolated["share"],
        "effectCertifiedTemplates": str(evidence_policy["effect_certified"]),
        "scalingGridPoints": scaling["grid_points"],
        "largestCandidateSet": scaling["largest_set"],
        "refusedCandidateSet": scaling["refused_size"],
        "enumerationCeiling": scaling["default_ceiling"],
        "flowActionCount": flow["actions"],
        "flowEdgeCount": flow["edges"],
        "flowOrderInversions": flow["inversions"],
        "flowOrderPairs": flow["pairs"],
        "flowCoveredTechniques": flow["covered"],
        "targetDomainSteps": locus["target_steps"],
        "boundaryDomainSteps": locus["boundary_steps"],
        "attackerDomainSteps": locus["attacker_steps"],
        "targetDomainShare": locus["target_share"],
        "targetDomainTemplates": locus["target_templates"],
        "boundaryDomainTemplates": locus["boundary_templates"],
        "attackerDomainTemplates": locus["attacker_templates"],
        "ourReachSteps": catalog_baseline["our_reach"],
        "baselineReachSteps": catalog_baseline["baseline_reach"],
        "baselineTechniqueCount": catalog_baseline["baseline_techniques"],
        "baselineUncoveredSteps": catalog_baseline["uncovered"],
        "baselineReachShare": catalog_baseline["baseline_share"],
        "stagetwoProposals": stage2["proposals"],
        "stagetwoAdmitted": stage2["admitted"],
        "stagetwoRejected": stage2["rejected"],
        "stagetwoTrustedReach": stage2["trusted_reach"],
        "stagetwoExtendedReach": stage2["extended_reach"],
        "stagetwoExtendedShare": stage2["extended_share"],
        "registeredPredicateNames": str(evidence_policy["registered"]),
        "effectPredicateNames": str(evidence_policy["effect_names"]),
        "safetyPredicateNames": str(evidence_policy["safety_names"]),
        "deepCampaignCount": str(len(DEEP_CAMPAIGNS)),
        "deepStepCount": str(baseline["steps"]),
        "rawAdmittedSteps": str(baseline["raw"]),
        "enrichedAdmittedSteps": str(baseline["enriched"]),
        "mechanismCommitments": str(commitments["mechanism"]),
        "bindingCommitments": str(commitments["binding"]),
        "totalCommitments": str(commitments["total"]),
        "bindingOccurrences": str(provenance["occurrences"]),
        "ctiEvidencedBindings": str(provenance["cti_evidenced"]),
        "environmentBindingPct": _percent(
            provenance["environment_determined"], provenance["occurrences"]
        ),
        "environmentBindingMinPct": f"{provenance['environment_rate_min'] * 100:.0f}",
        "environmentBindingMaxPct": f"{provenance['environment_rate_max'] * 100:.0f}",
        "systemIntroducedPct": _percent(
            provenance["system_introduced"], provenance["occurrences"]
        ),
        "activeTechniqueCount": str(_corpus_characterization()["active_techniques"]),
        "structureCampaignCount": str(_behavioral_structure()["campaigns"]),
        "structureMedianTechniques": str(_behavioral_structure()["median_techniques"]),
        "structureMedianShared": str(_behavioral_structure()["median_shared_techniques"]),
        "structureNearestJaccard": f"{_behavioral_structure()['observed']['mean_nearest_neighbor_jaccard']:.2f}",
        "structureNullNearestJaccard": f"{_behavioral_structure()['nearest_neighbor_null']['null_mean']:.2f}",
        "structureNullDraws": str(_behavioral_structure()["nearest_neighbor_null"]["draws"]),
        "structureNullExceeding": str(_behavioral_structure()["nearest_neighbor_null"]["draws_at_least_observed"]),
        "structureFamilyThreshold": f"{_behavioral_structure()['family_similarity']:.1f}",
        "structureFamilies": str(_behavioral_structure()["families"]),
        "campaignTechniqueCount": str(_corpus_characterization()["campaign_referenced"]),
        "campaignTechniquePct": f"{_corpus_characterization()['campaign_reference_rate'] * 100:.1f}",
        "intrusionSetTechniqueCount": str(
            _corpus_characterization()["intrusion_set_referenced"]
        ),
        "intrusionSetTechniquePct": f"{_corpus_characterization()['intrusion_set_reference_rate'] * 100:.1f}",
        "campaignOnlyTechniqueCount": str(_corpus_characterization()["campaign_only"]),
        "sharedTechniqueCount": str(_corpus_characterization()["referenced_by_both"]),
        "intrusionSetOnlyTechniqueCount": str(_corpus_characterization()["intrusion_set_only"]),
        "techniquesReferencedByNeither": str(
            _corpus_characterization()["referenced_by_neither"]
        ),
        "corpusCampaignCount": str(corpus["total_campaigns"]),
        "corpusActiveCampaignCount": str(_active_campaign_count()),
        "divergenceSteps": _divergence_totals()["steps"],
        "divergenceProposers": _divergence_totals()["proposers"],
        "divergenceDistinctDecisions": _divergence_totals()["distinct_decisions"],
        "divergenceAgreementPct": _divergence_totals()["agreement_pct"],
        "divergenceConvergedSteps": _divergence_totals()["converged_steps"],
        "deterministicDivergenceProposers": _divergence_totals()["det_proposers"],
        "deterministicDivergenceDistinct": _divergence_totals()["det_distinct"],
        "deterministicDivergenceConvergedSteps": _divergence_totals()["det_converged"],
        "deterministicReproducibleProposers": _divergence_totals()["det_reproducible"],
        "deterministicRepeatedProposers": _divergence_totals()["det_repeated"],
        "catalogOnlyDistinct": _divergence_totals()["catalog_only_distinct"],
        "catalogOnlyAgreementPct": _divergence_totals()["catalog_only_agreement"],
        "catalogOnlyConvergedSteps": _divergence_totals()["catalog_only_converged"],
        "catalogOnlyOutsideCatalog": _divergence_totals()["catalog_only_outside"],
        "convergenceObservations": str(_convergence_totals()["observations"]),
        "convergenceModelObservations": str(_convergence_totals()["model_observations"]),
        "convergenceProposerContributing": str(
            _convergence_totals()["proposer_contributing"]
        ),
        "derivedAdmittedSteps": str(_derived_environment_totals()["admitted"]),
        "derivedCampaignsWithAdmittedStep": str(_derived_environment_totals()["with_admitted_step"]),
        "convergenceDistinctPerCampaign": str(_convergence_totals()["distinct_per_campaign"]),
        "corpusStepCount": str(corpus["total_steps"]),
        "corpusSupportedSteps": str(corpus["catalog_supported_steps"]),
        "corpusCoveragePct": f"{corpus['catalog_coverage_rate'] * 100:.1f}",
        "corpusUnsupportedPct": f"{(1 - corpus['catalog_coverage_rate']) * 100:.1f}",
        "corpusDivergentSteps": str(corpus["evidence_divergent"]),
        "hypotheticalAdmitted": str(len(substitution["admitted_by_scope"]["hypothetical"])),
        "initialAdmitted": str(len(substitution["admitted_by_scope"]["initial"])),
        "sequentialAdmitted": str(len(substitution["admitted_by_scope"]["sequential"])),
    }


def render(macros: dict[str, str]) -> str:
    lines = [
        "% Generated by scripts/render_paper_macros.py from frozen evidence records.",
        "% Do not edit: regenerate with scripts/reproduce.py.",
    ]
    lines += [f"\\newcommand{{\\{name}}}{{{value}}}" for name, value in macros.items()]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    macros = build_macros()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(macros), encoding="utf-8")
    print(f"[paper-macros] wrote {len(macros)} macros to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
