#!/usr/bin/env python3
"""
Supplementary robustness and consistency checks for Paper 1.

Stress-tests two claims:
1. Campaign structure remains weak under binary-data similarity measures
   beyond Euclidean k-means (Hamming, Jaccard via agglomerative clustering).
2. Campaign-to-intrusion-set links in the Enterprise bundle often encode
   only partial overlap in either direction.
"""

from __future__ import annotations

import importlib.util
import json
import random
import statistics
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import pairwise_distances, silhouette_score


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYZE_CAMPAIGNS = Path(__file__).resolve().parent / "analyze_campaigns.py"
OUTPUT_JSON = PROJECT_ROOT / "results" / "paper1_robustness_provenance.json"
OUTPUT_MD = PROJECT_ROOT / "results" / "PAPER1_ROBUSTNESS_PROVENANCE.md"


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name or path.as_posix()


def load_analyze_campaigns_module():
    spec = importlib.util.spec_from_file_location("analyze_campaigns", ANALYZE_CAMPAIGNS)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import {ANALYZE_CAMPAIGNS}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_campaign_matrix(mod, nonempty_campaign_rows, by_id):
    observed_technique_ids = sorted(
        {
            technique_id
            for row in nonempty_campaign_rows
            for technique_id in row["technique_ids"]
        }
    )
    positions = {technique_id: index for index, technique_id in enumerate(observed_technique_ids)}
    matrix = np.zeros((len(nonempty_campaign_rows), len(observed_technique_ids)), dtype=int)
    for row_index, row in enumerate(nonempty_campaign_rows):
        for technique_id in row["technique_ids"]:
            matrix[row_index, positions[technique_id]] = 1
    return observed_technique_ids, matrix


def compute_agglomerative_silhouettes(matrix: np.ndarray) -> dict[str, object]:
    metrics = {}
    for metric in ["hamming", "jaccard"]:
        metric_input = matrix.astype(bool) if metric == "jaccard" else matrix
        distance_matrix = pairwise_distances(metric_input, metric=metric)
        per_k = {}
        cluster_sizes_k7 = []
        for k in range(2, 11):
            labels = AgglomerativeClustering(
                n_clusters=k,
                metric="precomputed",
                linkage="average",
            ).fit_predict(distance_matrix)
            silhouette = float(silhouette_score(distance_matrix, labels, metric="precomputed"))
            per_k[str(k)] = round(silhouette, 4)
            if k == 7:
                cluster_sizes_k7 = sorted(
                    [int((labels == label).sum()) for label in sorted(set(labels))],
                    reverse=True,
                )
        metrics[metric] = {
            "per_k": per_k,
            "k7_cluster_sizes": cluster_sizes_k7,
        }
    return metrics


def compute_lcs_sensitivity(mod, nonempty_campaign_rows, observed_technique_ids, by_id):
    rng = random.Random(42)
    technique_ranks = {}
    external_ids = {}
    for technique_id in observed_technique_ids:
        tactics = [
            mod.TACTIC_RANK.get(tactic, 99)
            for tactic in mod.get_tactics(by_id[technique_id])
        ]
        tactics = [rank for rank in tactics if rank != 99]
        technique_ranks[technique_id] = tactics or [99]
        external_ids[technique_id] = mod.get_external_id(by_id[technique_id])

    pair_indexes = list(combinations(range(len(nonempty_campaign_rows)), 2))
    mean_values = []
    median_values = []
    max_values = []
    for _ in range(200):
        sequences = []
        for row in nonempty_campaign_rows:
            ordered = sorted(
                row["technique_ids"],
                key=lambda technique_id: (
                    rng.choice(technique_ranks[technique_id]),
                    external_ids[technique_id],
                ),
            )
            sequences.append(
                [
                    external_ids[technique_id]
                    for technique_id in ordered
                    if external_ids[technique_id]
                ]
            )

        lcs_lengths = [
            mod.lcs_length(sequences[left_index], sequences[right_index])
            for left_index, right_index in pair_indexes
            if sequences[left_index] and sequences[right_index]
        ]
        mean_values.append(statistics.mean(lcs_lengths))
        median_values.append(float(statistics.median(lcs_lengths)))
        max_values.append(max(lcs_lengths))

    return {
        "mean_avg": round(statistics.mean(mean_values), 3),
        "mean_min": round(min(mean_values), 3),
        "mean_max": round(max(mean_values), 3),
        "median_avg": round(statistics.mean(median_values), 3),
        "median_min": round(min(median_values), 3),
        "median_max": round(max(median_values), 3),
        "max_avg": round(statistics.mean(max_values), 3),
        "max_min": min(max_values),
        "max_max": max(max_values),
    }


def compute_campaign_intrusion_overlap(mod, relationships, by_id, campaign_rows, intrusion_set_rows):
    campaign_by_id = {row["id"]: row for row in campaign_rows}
    intrusion_set_by_id = {row["id"]: row for row in intrusion_set_rows}
    attributed_pairs = []
    for relationship in relationships:
        if relationship.get("relationship_type") != "attributed-to" or not mod.is_active(relationship):
            continue
        source_ref = relationship.get("source_ref")
        target_ref = relationship.get("target_ref")
        if by_id.get(source_ref, {}).get("type") == "campaign" and by_id.get(target_ref, {}).get("type") == "intrusion-set":
            attributed_pairs.append((source_ref, target_ref))
        elif by_id.get(source_ref, {}).get("type") == "intrusion-set" and by_id.get(target_ref, {}).get("type") == "campaign":
            attributed_pairs.append((target_ref, source_ref))

    pair_stats = []
    for campaign_id, intrusion_set_id in attributed_pairs:
        campaign = campaign_by_id.get(campaign_id)
        intrusion_set = intrusion_set_by_id.get(intrusion_set_id)
        if not campaign or not intrusion_set:
            continue
        if not campaign["technique_ids"] or not intrusion_set["technique_ids"]:
            continue
        intersection = campaign["technique_ids"] & intrusion_set["technique_ids"]
        union = campaign["technique_ids"] | intrusion_set["technique_ids"]
        pair_stats.append(
            {
                "campaign": campaign["name"],
                "intrusion_set": intrusion_set["name"],
                "campaign_count": len(campaign["technique_ids"]),
                "intrusion_count": len(intrusion_set["technique_ids"]),
                "intersection": len(intersection),
                "campaign_in_set_pct": round(len(intersection) / len(campaign["technique_ids"]) * 100, 1),
                "set_in_campaign_pct": round(len(intersection) / len(intrusion_set["technique_ids"]) * 100, 1),
                "jaccard_pct": round(len(intersection) / len(union) * 100, 1),
                "campaign_only": len(campaign["technique_ids"] - intrusion_set["technique_ids"]),
                "set_only": len(intrusion_set["technique_ids"] - campaign["technique_ids"]),
            }
        )

    def summarize(key: str):
        values = [row[key] for row in pair_stats]
        return {
            "median": round(statistics.median(values), 1),
            "mean": round(statistics.mean(values), 1),
            "min": round(min(values), 1),
            "max": round(max(values), 1),
        }

    counts = {
        "pair_count": len(pair_stats),
        "set_in_campaign_below_25": sum(row["set_in_campaign_pct"] < 25 for row in pair_stats),
        "set_in_campaign_below_50": sum(row["set_in_campaign_pct"] < 50 for row in pair_stats),
        "set_in_campaign_below_75": sum(row["set_in_campaign_pct"] < 75 for row in pair_stats),
        "jaccard_below_25": sum(row["jaccard_pct"] < 25 for row in pair_stats),
        "jaccard_below_50": sum(row["jaccard_pct"] < 50 for row in pair_stats),
        "jaccard_below_75": sum(row["jaccard_pct"] < 75 for row in pair_stats),
    }

    examples = sorted(
        pair_stats,
        key=lambda row: (row["set_in_campaign_pct"], row["jaccard_pct"], row["campaign"]),
    )[:10]

    return {
        "counts": counts,
        "campaign_in_set_pct": summarize("campaign_in_set_pct"),
        "set_in_campaign_pct": summarize("set_in_campaign_pct"),
        "jaccard_pct": summarize("jaccard_pct"),
        "lowest_overlap_examples": examples,
    }


def write_markdown(report: dict[str, object]) -> None:
    lines = [
        "# Paper 1 Robustness Provenance",
        "",
        f"- Bundle: `{report['bundle_path']}`",
        f"- Generated at (UTC): `{report['generated_at_utc']}`",
        "",
        "## Alternative Binary-Distance Clustering",
        "",
    ]
    for metric, details in report["agglomerative_binary_metrics"].items():
        per_k = details["per_k"]
        lines.append(
            f"- `{metric}` average-linkage agglomerative clustering: "
            f"`k=7` silhouette `{per_k['7']}` with cluster sizes `{details['k7_cluster_sizes']}`; "
            f"`k=2..10` silhouettes `{per_k}`."
        )

    lcs = report["lcs_randomized_tactic_sensitivity"]
    lines.extend(
        [
            "",
            "## Randomized Tactic-Assignment LCS Sensitivity",
            "",
            f"- Mean LCS across 200 trials: average `{lcs['mean_avg']}`, range `{lcs['mean_min']}`--`{lcs['mean_max']}`.",
            f"- Median LCS across 200 trials: average `{lcs['median_avg']}`, range `{lcs['median_min']}`--`{lcs['median_max']}`.",
            f"- Max LCS across 200 trials: average `{lcs['max_avg']}`, range `{lcs['max_min']}`--`{lcs['max_max']}`.",
            "",
            "## Campaign / Intrusion-Set Overlap",
            "",
        ]
    )
    overlap = report["campaign_intrusion_overlap"]
    counts = overlap["counts"]
    lines.extend(
        [
            f"- Attributed campaign/intrusion-set pairs with techniques on both sides: `{counts['pair_count']}`.",
            f"- Intrusion-set techniques observed in the linked campaign (|C&I|/|I|): median `{overlap['set_in_campaign_pct']['median']}`%, mean `{overlap['set_in_campaign_pct']['mean']}`%, min `{overlap['set_in_campaign_pct']['min']}`%, max `{overlap['set_in_campaign_pct']['max']}`%.",
            f"- Campaign techniques shared with the linked intrusion set (|C&I|/|C|): median `{overlap['campaign_in_set_pct']['median']}`%, mean `{overlap['campaign_in_set_pct']['mean']}`%, min `{overlap['campaign_in_set_pct']['min']}`%, max `{overlap['campaign_in_set_pct']['max']}`%.",
            f"- Jaccard overlap: median `{overlap['jaccard_pct']['median']}`%, mean `{overlap['jaccard_pct']['mean']}`%, min `{overlap['jaccard_pct']['min']}`%, max `{overlap['jaccard_pct']['max']}`%.",
            "",
            "### Lowest-Overlap Examples",
            "",
        ]
    )
    for row in overlap["lowest_overlap_examples"]:
        lines.append(
            f"- `{row['campaign']}` / `{row['intrusion_set']}`: "
            f"|C&I|/|I|={row['set_in_campaign_pct']}%, "
            f"|C&I|/|C|={row['campaign_in_set_pct']}%, "
            f"J={row['jaccard_pct']}% "
            f"(|C&I|={row['intersection']}, |C|={row['campaign_count']}, |I|={row['intrusion_count']})."
        )

    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    mod = load_analyze_campaigns_module()
    objects, by_id = mod.load_bundle(mod.DEFAULT_BUNDLE)
    campaigns = [obj for obj in objects if obj.get("type") == "campaign" and mod.is_active(obj)]
    intrusion_sets = [obj for obj in objects if obj.get("type") == "intrusion-set" and mod.is_active(obj)]
    relationships = [obj for obj in objects if obj.get("type") == "relationship"]
    uses_relationships = [
        obj
        for obj in relationships
        if obj.get("relationship_type") == "uses"
    ]
    forward_index = mod.build_forward_index(uses_relationships)

    campaign_rows, nonempty_campaign_rows, _, _ = mod.collect_campaign_data(
        campaigns, by_id, forward_index
    )
    intrusion_set_rows, _, _ = mod.collect_intrusion_set_data(
        intrusion_sets, by_id, forward_index
    )
    observed_technique_ids, matrix = build_campaign_matrix(mod, nonempty_campaign_rows, by_id)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "bundle_path": display_path(mod.DEFAULT_BUNDLE),
        "campaign_matrix_shape": list(matrix.shape),
        "campaign_matrix_density": round(float(matrix.mean()), 6),
        "agglomerative_binary_metrics": compute_agglomerative_silhouettes(matrix),
        "lcs_randomized_tactic_sensitivity": compute_lcs_sensitivity(
            mod, nonempty_campaign_rows, observed_technique_ids, by_id
        ),
        "campaign_intrusion_overlap": compute_campaign_intrusion_overlap(
            mod, relationships, by_id, campaign_rows, intrusion_set_rows
        ),
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report)
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
