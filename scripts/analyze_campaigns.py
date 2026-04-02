#!/usr/bin/env python3
"""
Compute Paper 1 values from the current ATT&CK Enterprise bundle.

The script keeps a single canonical path for Paper 1 macros:
  - bundle-derived counts and overlap statistics
  - classifier-derived translatability counts
  - experiment-design case-study constants
  - clustering and LCS measurements
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"
OUTPUT_JSON = PROJECT_ROOT / "results" / "paper1_values_provenance.json"
OUTPUT_MD = PROJECT_ROOT / "results" / "PAPER1_VALUES_PROVENANCE.md"

TACTIC_ORDER = [
    "reconnaissance",
    "resource-development",
    "initial-access",
    "execution",
    "persistence",
    "privilege-escalation",
    "defense-evasion",
    "credential-access",
    "discovery",
    "lateral-movement",
    "collection",
    "command-and-control",
    "exfiltration",
    "impact",
]
TACTIC_RANK = {tactic: index for index, tactic in enumerate(TACTIC_ORDER)}
CONCRETE_HOST_PLATFORMS = {
    "Windows",
    "Linux",
    "macOS",
    "Containers",
    "ESXi",
    "Network Devices",
}
KMEANS_K = 7
CASE_STUDY_RUNS = 10


@dataclass(frozen=True)
class CaseStudySpec:
    display_name: str
    stix_name: str
    stix_type: str
    local_campaign_id: str | None
    runs: int


CASE_STUDIES = [
    CaseStudySpec(
        display_name="ShadowRay",
        stix_name="ShadowRay",
        stix_type="campaign",
        local_campaign_id="0.shadowray",
        runs=CASE_STUDY_RUNS,
    ),
    CaseStudySpec(
        display_name="Soft Cell",
        stix_name="GALLIUM",
        stix_type="intrusion-set",
        local_campaign_id=None,
        runs=CASE_STUDY_RUNS,
    ),
]

LATEX_GROUPS = [
    (
        "Dataset counts",
        [
            "nCampaignsTotal",
            "nCampaigns",
            "nIntrusionSets",
            "nRelationships",
            "nAttackPatternObjects",
            "nTechniquesAnalysis",
            "nComposedObjects",
        ],
    ),
    (
        "Campaign technique coverage",
        [
            "campaignCoveragePct",
            "campaignCoverageUnusedPct",
            "campaignTechniqueCount",
            "intrusionSetCoveragePct",
            "intrusionSetTechniqueCount",
            "sharedTechniqueCount",
            "campaignOnlyCount",
            "intrusionSetOnlyCount",
            "unusedTechniqueCount",
        ],
    ),
    (
        "Venn diagram percentages",
        [
            "campaignOnlyPct",
            "sharedPct",
            "intrusionSetOnlyPct",
            "unusedPct",
        ],
    ),
    (
        "Technique frequency",
        [
            "topTechniqueId",
            "topTechniqueLabel",
            "topTechniqueInCampaigns",
            "topTechniquePct",
        ],
    ),
    (
        "Intrusion sets",
        [
            "nIntrusionSetsWithTechniques",
            "intrusionSetWithTechniquesPct",
            "nIntrusionSetsEmpty",
            "intrusionSetEmptyPct",
            "intrusionSetTechRefs",
            "intrusionSetTechAvg",
        ],
    ),
    (
        "Emulation",
        [
            "nPlatformAgnosticTechniques",
            "nTranslatableTechniques",
            "nCaseStudyCampaigns",
            "caseStudyRunsEach",
        ],
    ),
    (
        "Clustering and LCS",
        [
            "silhouetteScore",
            "silhouetteBaselineMean",
            "silhouetteBaselineStd",
            "lcsLengthMean",
            "lcsLengthMedian",
            "lcsLengthMax",
        ],
    ),
]


def is_active(obj: dict[str, Any]) -> bool:
    return not obj.get("revoked", False) and not obj.get("x_mitre_deprecated", False)


def load_bundle(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    objects = bundle.get("objects", [])
    by_id = {obj["id"]: obj for obj in objects if "id" in obj}
    return objects, by_id


def get_external_id(obj: dict[str, Any]) -> str:
    for reference in obj.get("external_references", []):
        if reference.get("source_name") == "mitre-attack":
            return reference.get("external_id", "")
    return ""


def get_tactics(obj: dict[str, Any]) -> list[str]:
    return [
        phase.get("phase_name", "")
        for phase in obj.get("kill_chain_phases", [])
        if phase.get("kill_chain_name") == "mitre-attack"
    ]


def get_tactic_rank(obj: dict[str, Any]) -> int:
    ranks = [TACTIC_RANK.get(tactic, 99) for tactic in get_tactics(obj)]
    return min(ranks) if ranks else 99


def build_forward_index(
    relationships: list[dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    index: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for relationship in relationships:
        source_ref = relationship.get("source_ref", "")
        target_ref = relationship.get("target_ref", "")
        relationship_type = relationship.get("relationship_type", "")
        if source_ref and target_ref and relationship_type:
            index[source_ref][relationship_type].append(target_ref)
    return index


def euclidean_sq(left: list[float], right: list[float]) -> float:
    return sum((left_value - right_value) ** 2 for left_value, right_value in zip(left, right))


def centroid(points: list[list[float]]) -> list[float]:
    point_count = len(points)
    dimension_count = len(points[0])
    return [
        sum(point[index] for point in points) / point_count
        for index in range(dimension_count)
    ]


def kmeans(
    matrix: list[list[float]],
    k: int,
    max_iter: int = 300,
    seed: int = 42,
) -> tuple[list[int], list[list[float]]]:
    rng = random.Random(seed)
    point_count = len(matrix)
    centers = [list(matrix[rng.randrange(point_count)])]

    for _ in range(k - 1):
        distances = [min(euclidean_sq(point, center) for center in centers) for point in matrix]
        total_distance = sum(distances)
        if total_distance == 0:
            centers.append(list(matrix[rng.randrange(point_count)]))
            continue

        threshold = rng.random() * total_distance
        cumulative = 0.0
        for index, distance in enumerate(distances):
            cumulative += distance
            if cumulative >= threshold:
                centers.append(list(matrix[index]))
                break
        else:
            centers.append(list(matrix[-1]))

    labels = [0] * point_count
    for _ in range(max_iter):
        new_labels = [
            min(range(k), key=lambda cluster: euclidean_sq(matrix[index], centers[cluster]))
            for index in range(point_count)
        ]
        if new_labels == labels:
            break
        labels = new_labels
        for cluster in range(k):
            cluster_points = [
                matrix[index]
                for index in range(point_count)
                if labels[index] == cluster
            ]
            if cluster_points:
                centers[cluster] = centroid(cluster_points)

    return labels, centers


def silhouette_coefficient(matrix: list[list[float]], labels: list[int]) -> float:
    point_count = len(matrix)
    if point_count < 2:
        return 0.0

    clusters: dict[int, list[int]] = defaultdict(list)
    for index, label in enumerate(labels):
        clusters[label].append(index)

    scores = []
    for index in range(point_count):
        same_cluster = [member for member in clusters[labels[index]] if member != index]
        if not same_cluster:
            scores.append(0.0)
            continue

        intra_cluster = sum(
            euclidean_sq(matrix[index], matrix[member]) ** 0.5
            for member in same_cluster
        ) / len(same_cluster)

        nearest_cluster = float("inf")
        for other_label, members in clusters.items():
            if other_label == labels[index]:
                continue
            mean_distance = sum(
                euclidean_sq(matrix[index], matrix[member]) ** 0.5
                for member in members
            ) / len(members)
            nearest_cluster = min(nearest_cluster, mean_distance)

        if nearest_cluster == float("inf"):
            scores.append(0.0)
            continue

        denominator = max(intra_cluster, nearest_cluster)
        scores.append((nearest_cluster - intra_cluster) / denominator if denominator else 0.0)

    return sum(scores) / len(scores)


def lcs_length(left: list[str], right: list[str]) -> int:
    if not left or not right:
        return 0

    left_length = len(left)
    right_length = len(right)
    table = [[0] * (right_length + 1) for _ in range(left_length + 1)]
    for left_index in range(1, left_length + 1):
        for right_index in range(1, right_length + 1):
            if left[left_index - 1] == right[right_index - 1]:
                table[left_index][right_index] = table[left_index - 1][right_index - 1] + 1
            else:
                table[left_index][right_index] = max(
                    table[left_index - 1][right_index],
                    table[left_index][right_index - 1],
                )
    return table[left_length][right_length]


def format_decimal(value: float, digits: int) -> str:
    return f"{value:.{digits}f}"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def collect_campaign_data(
    campaigns: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    forward_index: dict[str, dict[str, list[str]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str], Counter[str]]:
    campaign_rows = []
    nonempty_campaign_rows = []
    campaign_techniques = set()
    campaign_frequency: Counter[str] = Counter()

    for campaign in campaigns:
        technique_ids = {
            target_id
            for target_id in forward_index.get(campaign["id"], {}).get("uses", [])
            if by_id.get(target_id, {}).get("type") == "attack-pattern"
            and is_active(by_id[target_id])
        }
        row = {
            "id": campaign["id"],
            "name": campaign.get("name", campaign["id"]),
            "technique_ids": technique_ids,
        }
        campaign_rows.append(row)
        if technique_ids:
            nonempty_campaign_rows.append(row)
            campaign_techniques.update(technique_ids)
            for technique_id in technique_ids:
                campaign_frequency[technique_id] += 1

    return campaign_rows, nonempty_campaign_rows, campaign_techniques, campaign_frequency


def collect_intrusion_set_data(
    intrusion_sets: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    forward_index: dict[str, dict[str, list[str]]],
) -> tuple[list[dict[str, Any]], set[str], int]:
    rows = []
    intrusion_set_techniques = set()
    technique_references = 0

    for intrusion_set in intrusion_sets:
        technique_ids = {
            target_id
            for target_id in forward_index.get(intrusion_set["id"], {}).get("uses", [])
            if by_id.get(target_id, {}).get("type") == "attack-pattern"
            and is_active(by_id[target_id])
        }
        rows.append(
            {
                "id": intrusion_set["id"],
                "name": intrusion_set.get("name", intrusion_set["id"]),
                "technique_ids": technique_ids,
            }
        )
        intrusion_set_techniques.update(technique_ids)
        technique_references += len(technique_ids)

    return rows, intrusion_set_techniques, technique_references


def compute_clustering_metrics(
    nonempty_campaign_rows: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    observed_technique_ids = sorted(
        {
            technique_id
            for row in nonempty_campaign_rows
            for technique_id in row["technique_ids"]
        }
    )
    technique_positions = {
        technique_id: index for index, technique_id in enumerate(observed_technique_ids)
    }
    matrix = []
    for row in nonempty_campaign_rows:
        vector = [0.0] * len(observed_technique_ids)
        for technique_id in row["technique_ids"]:
            vector[technique_positions[technique_id]] = 1.0
        matrix.append(vector)

    labels, _ = kmeans(matrix, k=KMEANS_K, seed=42)
    silhouette = silhouette_coefficient(matrix, labels)

    density = sum(sum(vector) for vector in matrix) / (len(matrix) * len(matrix[0]))
    random_silhouettes = []
    rng = random.Random(42)
    for _ in range(1000):
        random_matrix = [
            [1.0 if rng.random() < density else 0.0 for _ in range(len(matrix[0]))]
            for _ in range(len(matrix))
        ]
        random_labels, _ = kmeans(random_matrix, k=KMEANS_K, seed=rng.randint(0, 100000))
        random_silhouettes.append(silhouette_coefficient(random_matrix, random_labels))

    sequences = []
    for row in nonempty_campaign_rows:
        ordered = sorted(
            row["technique_ids"],
            key=lambda technique_id: (
                get_tactic_rank(by_id[technique_id]),
                get_external_id(by_id[technique_id]),
            ),
        )
        sequences.append(
            [
                get_external_id(by_id[technique_id])
                for technique_id in ordered
                if get_external_id(by_id[technique_id])
            ]
        )

    lcs_lengths = [
        lcs_length(sequences[left_index], sequences[right_index])
        for left_index, right_index in combinations(range(len(sequences)), 2)
        if sequences[left_index] and sequences[right_index]
    ]

    return {
        "silhouetteScore": format_decimal(round(silhouette, 2), 2),
        "silhouetteBaselineMean": format_decimal(round(statistics.mean(random_silhouettes), 2), 2),
        "silhouetteBaselineStd": format_decimal(round(statistics.stdev(random_silhouettes), 2), 2),
        "lcsLengthMean": format_decimal(round(statistics.mean(lcs_lengths), 1), 1),
        "lcsLengthMedian": format_decimal(round(float(statistics.median(lcs_lengths)), 1), 1),
        "lcsLengthMax": str(max(lcs_lengths)),
    }


def compute_platform_agnostic_techniques(
    techniques: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    platform_agnostic = []
    for technique in techniques:
        platforms = set(technique.get("x_mitre_platforms", []))
        if technique.get("x_mitre_is_subtechnique"):
            continue
        if platforms & CONCRETE_HOST_PLATFORMS:
            continue
        platform_agnostic.append(
            {
                "technique_id": get_external_id(technique),
                "name": technique.get("name", ""),
                "platforms": sorted(platforms),
                "tactics": sorted(get_tactics(technique)),
            }
        )

    platform_agnostic.sort(key=lambda item: item["technique_id"])
    return platform_agnostic


def build_case_study_report(
    objects: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    unique_runs = {case_study.runs for case_study in CASE_STUDIES}
    if len(unique_runs) != 1:
        raise ValueError("Paper 1 case-study runs are not uniform.")

    report = []
    for case_study in CASE_STUDIES:
        match = next(
            (
                obj
                for obj in objects
                if obj.get("type") == case_study.stix_type
                and obj.get("name") == case_study.stix_name
                and is_active(obj)
            ),
            None,
        )
        if match is None:
            raise ValueError(
                f"Could not find active {case_study.stix_type} named {case_study.stix_name!r}."
            )

        description = match.get("description", "")
        report.append(
            {
                "display_name": case_study.display_name,
                "stix_name": case_study.stix_name,
                "stix_type": case_study.stix_type,
                "stix_id": match["id"],
                "local_campaign_id": case_study.local_campaign_id,
                "runs": case_study.runs,
                "description_mentions_display_name": case_study.display_name.lower() in description.lower(),
            }
        )

    return report, unique_runs.pop()


def compute_paper1_values(bundle_path: Path) -> dict[str, Any]:
    objects, by_id = load_bundle(bundle_path)
    campaigns = [obj for obj in objects if obj.get("type") == "campaign" and is_active(obj)]
    intrusion_sets = [
        obj for obj in objects if obj.get("type") == "intrusion-set" and is_active(obj)
    ]
    techniques = [
        obj for obj in objects if obj.get("type") == "attack-pattern" and is_active(obj)
    ]
    relationships = [
        obj
        for obj in objects
        if obj.get("type") == "relationship" and obj.get("relationship_type") == "uses"
    ]
    forward_index = build_forward_index(relationships)

    campaign_rows, nonempty_campaign_rows, campaign_techniques, campaign_frequency = collect_campaign_data(
        campaigns,
        by_id,
        forward_index,
    )
    intrusion_set_rows, intrusion_set_techniques, intrusion_set_technique_refs = collect_intrusion_set_data(
        intrusion_sets,
        by_id,
        forward_index,
    )

    top_technique_id, top_technique_count = campaign_frequency.most_common(1)[0]
    top_technique = by_id[top_technique_id]
    all_active_technique_ids = {technique["id"] for technique in techniques}
    shared_techniques = campaign_techniques & intrusion_set_techniques
    campaign_only_techniques = campaign_techniques - intrusion_set_techniques
    intrusion_set_only_techniques = intrusion_set_techniques - campaign_techniques
    unused_techniques = all_active_technique_ids - (campaign_techniques | intrusion_set_techniques)
    populated_intrusion_sets = [
        row for row in intrusion_set_rows if row["technique_ids"]
    ]
    empty_intrusion_sets = [
        row for row in intrusion_set_rows if not row["technique_ids"]
    ]

    platform_agnostic_techniques = compute_platform_agnostic_techniques(techniques)
    case_studies, runs_per_case_study = build_case_study_report(objects)

    macro_values = {
        "nCampaignsTotal": str(len(campaign_rows)),
        "nCampaigns": str(len(nonempty_campaign_rows)),
        "nIntrusionSets": str(len(intrusion_sets)),
        "nRelationships": str(len(relationships)),
        "nAttackPatternObjects": str(len(techniques)),
        "nTechniquesAnalysis": str(len(techniques)),
        "nComposedObjects": str(len(objects)),
        "campaignCoveragePct": format_decimal(
            len(campaign_techniques) / len(techniques) * 100,
            1,
        ),
        "campaignCoverageUnusedPct": format_decimal(
            len(unused_techniques | intrusion_set_only_techniques) / len(techniques) * 100,
            1,
        ),
        "campaignTechniqueCount": str(len(campaign_techniques)),
        "intrusionSetCoveragePct": format_decimal(
            len(intrusion_set_techniques) / len(techniques) * 100,
            1,
        ),
        "intrusionSetTechniqueCount": str(len(intrusion_set_techniques)),
        "sharedTechniqueCount": str(len(shared_techniques)),
        "campaignOnlyCount": str(len(campaign_only_techniques)),
        "intrusionSetOnlyCount": str(len(intrusion_set_only_techniques)),
        "unusedTechniqueCount": str(len(unused_techniques)),
        "campaignOnlyPct": format_decimal(
            len(campaign_only_techniques) / len(techniques) * 100,
            1,
        ),
        "sharedPct": format_decimal(
            len(shared_techniques) / len(techniques) * 100,
            1,
        ),
        "intrusionSetOnlyPct": format_decimal(
            len(intrusion_set_only_techniques) / len(techniques) * 100,
            1,
        ),
        "unusedPct": format_decimal(
            len(unused_techniques) / len(techniques) * 100,
            1,
        ),
        "topTechniqueId": get_external_id(top_technique),
        "topTechniqueLabel": top_technique.get("name", ""),
        "topTechniqueInCampaigns": str(top_technique_count),
        "topTechniquePct": str(
            round(top_technique_count / len(nonempty_campaign_rows) * 100)
        ),
        "nIntrusionSetsWithTechniques": str(len(populated_intrusion_sets)),
        "intrusionSetWithTechniquesPct": format_decimal(
            len(populated_intrusion_sets) / len(intrusion_sets) * 100,
            1,
        ),
        "nIntrusionSetsEmpty": str(len(empty_intrusion_sets)),
        "intrusionSetEmptyPct": format_decimal(
            len(empty_intrusion_sets) / len(intrusion_sets) * 100,
            1,
        ),
        "intrusionSetTechRefs": str(intrusion_set_technique_refs),
        "intrusionSetTechAvg": format_decimal(
            intrusion_set_technique_refs / len(populated_intrusion_sets),
            1,
        ),
        "nPlatformAgnosticTechniques": str(len(platform_agnostic_techniques)),
        "nTranslatableTechniques": str(len(techniques) - len(platform_agnostic_techniques)),
        "nCaseStudyCampaigns": str(len(case_studies)),
        "caseStudyRunsEach": str(runs_per_case_study),
    }
    macro_values.update(compute_clustering_metrics(nonempty_campaign_rows, by_id))

    return {
        "generated_at": datetime.now().isoformat(),
        "bundle_path": display_path(bundle_path),
        "macro_values": macro_values,
        "provenance": {
            "platform_agnostic_classifier": {
                "description": (
                    "Active top-level ATT&CK techniques without a concrete host platform "
                    f"({', '.join(sorted(CONCRETE_HOST_PLATFORMS))})."
                ),
                "count": len(platform_agnostic_techniques),
                "techniques": platform_agnostic_techniques,
            },
            "case_studies": case_studies,
            "counts": {
                "campaign_rows": len(campaign_rows),
                "campaign_rows_with_techniques": len(nonempty_campaign_rows),
                "intrusion_sets": len(intrusion_sets),
                "intrusion_sets_with_techniques": len(populated_intrusion_sets),
                "intrusion_sets_without_techniques": len(empty_intrusion_sets),
                "active_attack_patterns": len(techniques),
                "uses_relationships": len(relationships),
                "total_bundle_objects": len(objects),
            },
        },
    }


def render_values_tex(report: dict[str, Any]) -> str:
    macro_values = report["macro_values"]
    lines = [
        "% Measurement values for Paper 1 (STICKS)",
        f"% Bundle: {report['bundle_path']}",
        "% Computed by: python3 sticks/scripts/analyze_campaigns.py --bundle sticks/data/stix/enterprise-attack.json --output-latex",
        "%",
        "% Platform-agnostic techniques are active top-level ATT&CK techniques without",
        "% a concrete host platform among Windows, Linux, macOS, Containers, ESXi,",
        "% or Network Devices.",
        "",
    ]

    for heading, macro_names in LATEX_GROUPS:
        lines.append(f"% --- {heading} ---")
        for macro_name in macro_names:
            lines.append(f"\\newcommand{{\\{macro_name}}}{{{macro_values[macro_name]}}}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_report(report: dict[str, Any]) -> None:
    OUTPUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    classifier = report["provenance"]["platform_agnostic_classifier"]
    case_studies = report["provenance"]["case_studies"]
    counts = report["provenance"]["counts"]
    lines = [
        "# Paper 1 Values Provenance",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Bundle: `{report['bundle_path']}`",
        "",
        "## Counts",
        "",
        f"- Active campaigns: `{counts['campaign_rows']}`",
        f"- Active campaigns with techniques: `{counts['campaign_rows_with_techniques']}`",
        f"- Active intrusion sets: `{counts['intrusion_sets']}`",
        f"- Intrusion sets with techniques: `{counts['intrusion_sets_with_techniques']}`",
        f"- Intrusion sets without techniques: `{counts['intrusion_sets_without_techniques']}`",
        f"- Active attack-pattern objects: `{counts['active_attack_patterns']}`",
        f"- `uses` relationships: `{counts['uses_relationships']}`",
        f"- Total objects in analyzed bundle: `{counts['total_bundle_objects']}`",
        "",
        "## Platform-Agnostic Classifier",
        "",
        f"- Definition: {classifier['description']}",
        f"- Count: `{classifier['count']}`",
        "",
        "### Included Techniques",
        "",
    ]
    lines.extend(
        f"- `{item['technique_id']}` {item['name']} ({', '.join(item['platforms']) or 'no platforms'})"
        for item in classifier["techniques"]
    )
    lines.extend(
        [
            "",
            "## Case Studies",
            "",
        ]
    )
    lines.extend(
        (
            f"- `{item['display_name']}` -> `{item['stix_name']}` "
            f"({item['stix_type']}, runs={item['runs']}, "
            f"local_campaign_id={item['local_campaign_id'] or 'n/a'}, "
            f"description_mentions_display_name={item['description_mentions_display_name']})"
        )
        for item in case_studies
    )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        default=str(DEFAULT_BUNDLE),
        help="Path to the Enterprise ATT&CK STIX bundle JSON.",
    )
    parser.add_argument(
        "--output-latex",
        action="store_true",
        help="Print the full Paper 1 values.tex content to stdout.",
    )
    args = parser.parse_args()

    report = compute_paper1_values(Path(args.bundle))
    write_report(report)
    latex_text = render_values_tex(report)

    if args.output_latex:
        sys.stdout.write(latex_text)
        return

    macro_values = report["macro_values"]
    print("Paper 1 values generated from canonical sources:")
    print(f"  campaigns with techniques   : {macro_values['nCampaigns']}")
    print(f"  active attack-patterns      : {macro_values['nTechniquesAnalysis']}")
    print(f"  campaign coverage           : {macro_values['campaignCoveragePct']}%")
    print(f"  intrusion-set coverage      : {macro_values['intrusionSetCoveragePct']}%")
    print(
        "  platform-agnostic techniques: "
        f"{macro_values['nPlatformAgnosticTechniques']}"
    )
    print(f"  silhouette score            : {macro_values['silhouetteScore']}")
    print(f"  LCS mean / median / max     : {macro_values['lcsLengthMean']} / "
          f"{macro_values['lcsLengthMedian']} / {macro_values['lcsLengthMax']}")
    print(f"  report json                 : {OUTPUT_JSON}")
    print(f"  report md                   : {OUTPUT_MD}")
    print("  values.tex stdout           : use --output-latex")


if __name__ == "__main__":
    main()
