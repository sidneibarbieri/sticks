#!/usr/bin/env python3
"""
Measure positive-evidence identifiability for Paper 1 ATT&CK profiles.

Given only the set of ATT&CK techniques attributed to a campaign or
intrusion set, how many positive technique observations are sufficient
to distinguish that profile from the others in the same corpus?

Reports:
- whether a profile is distinguishable by positive technique evidence alone;
- the minimum size of a distinguishing technique witness, when it exists;
- scope curves showing how identifiability changes when tiny profiles are
  filtered out.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"
OUTPUT_JSON = PROJECT_ROOT / "results" / "paper1_identifiability_provenance.json"
OUTPUT_MD = PROJECT_ROOT / "results" / "PAPER1_IDENTIFIABILITY_PROVENANCE.md"


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


def collect_profiles(
    objects: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    forward_index: dict[str, dict[str, list[str]]],
    object_type: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for obj in objects:
        if obj.get("type") != object_type or not is_active(obj):
            continue

        technique_ids = {
            target_id
            for target_id in forward_index.get(obj["id"], {}).get("uses", [])
            if by_id.get(target_id, {}).get("type") == "attack-pattern"
            and is_active(by_id[target_id])
        }
        if not technique_ids:
            continue

        rows.append(
            {
                "id": obj["id"],
                "name": obj.get("name", obj["id"]),
                "technique_ids": frozenset(technique_ids),
            }
        )

    rows.sort(key=lambda row: (row["name"], row["id"]))
    return rows


def reduce_difference_sets(
    difference_sets: tuple[frozenset[str], ...] | list[frozenset[str]],
) -> tuple[frozenset[str], ...]:
    unique = sorted(
        set(difference_sets),
        key=lambda item: (len(item), tuple(sorted(item))),
    )
    reduced: list[frozenset[str]] = []
    for candidate in unique:
        if any(existing <= candidate for existing in reduced):
            continue
        reduced = [existing for existing in reduced if not candidate <= existing]
        reduced.append(candidate)
    return tuple(reduced)


def greedy_witness(difference_sets: tuple[frozenset[str], ...]) -> tuple[str, ...]:
    remaining = list(difference_sets)
    witness: list[str] = []
    while remaining:
        coverage = Counter(
            technique_id
            for difference_set in remaining
            for technique_id in difference_set
        )
        technique_id = min(
            coverage,
            key=lambda item: (-coverage[item], item),
        )
        witness.append(technique_id)
        remaining = [
            difference_set
            for difference_set in remaining
            if technique_id not in difference_set
        ]
    return tuple(sorted(witness))


def disjoint_family_lower_bound(difference_sets: tuple[frozenset[str], ...]) -> int:
    used: set[str] = set()
    count = 0
    for difference_set in sorted(difference_sets, key=lambda item: (len(item), tuple(sorted(item)))):
        if difference_set.isdisjoint(used):
            count += 1
            used.update(difference_set)
    return count


def find_minimum_witness(
    difference_sets: tuple[frozenset[str], ...] | list[frozenset[str]],
) -> tuple[str, ...]:
    reduced = reduce_difference_sets(tuple(difference_sets))
    if not reduced:
        return ()

    best = greedy_witness(reduced)

    def search(
        remaining: tuple[frozenset[str], ...],
        chosen: tuple[str, ...],
    ) -> None:
        nonlocal best

        if not remaining:
            candidate = tuple(sorted(chosen))
            if len(candidate) < len(best) or (
                len(candidate) == len(best) and candidate < best
            ):
                best = candidate
            return

        if len(chosen) >= len(best):
            return

        lower_bound = disjoint_family_lower_bound(remaining)
        if len(chosen) + lower_bound >= len(best):
            return

        pivot = min(remaining, key=lambda item: (len(item), tuple(sorted(item))))
        candidates = sorted(
            pivot,
            key=lambda technique_id: (
                -sum(1 for difference_set in remaining if technique_id in difference_set),
                technique_id,
            ),
        )

        for technique_id in candidates:
            next_remaining = reduce_difference_sets(
                tuple(
                    difference_set
                    for difference_set in remaining
                    if technique_id not in difference_set
                )
            )
            search(next_remaining, chosen + (technique_id,))

    search(reduced, ())
    return best


def build_threshold_curve(
    profile_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    max_size = max(row["technique_count"] for row in profile_rows)
    curve: list[dict[str, Any]] = []
    for threshold in range(1, max_size + 1):
        sample = [row for row in profile_rows if row["technique_count"] >= threshold]
        if not sample:
            continue
        finite_rows = [
            row for row in sample if row["min_witness_size"] is not None
        ]
        finite_sizes = [row["min_witness_size"] for row in finite_rows]
        curve.append(
            {
                "min_profile_technique_count": threshold,
                "sample_size": len(sample),
                "identifiable_count": len(finite_rows),
                "identifiable_pct": round(len(finite_rows) / len(sample) * 100, 1),
                "impossible_count": len(sample) - len(finite_rows),
                "max_witness_size": max(finite_sizes) if finite_sizes else None,
            }
        )
    return curve


def summarize_profiles(
    label: str,
    profiles: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    analyzed_rows: list[dict[str, Any]] = []
    witness_distribution: Counter[int] = Counter()

    for index, focal in enumerate(profiles):
        blockers = []
        difference_sets: list[frozenset[str]] = []
        for other_index, other in enumerate(profiles):
            if index == other_index:
                continue
            difference = focal["technique_ids"] - other["technique_ids"]
            if not difference:
                blockers.append(other["name"])
            else:
                difference_sets.append(frozenset(difference))

        witness_technique_ids: tuple[str, ...] | None
        if blockers:
            witness_technique_ids = None
        else:
            witness_technique_ids = find_minimum_witness(tuple(difference_sets))

        witness_external_ids = []
        witness_names = []
        if witness_technique_ids:
            for technique_id in witness_technique_ids:
                technique = by_id[technique_id]
                witness_external_ids.append(get_external_id(technique))
                witness_names.append(technique.get("name", technique_id))

        row = {
            "id": focal["id"],
            "name": focal["name"],
            "technique_count": len(focal["technique_ids"]),
            "min_witness_size": len(witness_technique_ids) if witness_technique_ids is not None else None,
            "witness_technique_ids": list(witness_external_ids),
            "witness_technique_names": witness_names,
            "blocker_count": len(blockers),
            "blocker_names": blockers,
        }
        analyzed_rows.append(row)
        if row["min_witness_size"] is not None:
            witness_distribution[row["min_witness_size"]] += 1

    technique_counts = [row["technique_count"] for row in analyzed_rows]
    finite_rows = [row for row in analyzed_rows if row["min_witness_size"] is not None]
    finite_sizes = [row["min_witness_size"] for row in finite_rows]
    impossible_rows = [row for row in analyzed_rows if row["min_witness_size"] is None]

    summary: dict[str, Any] = {
        "label": label,
        "profile_count": len(analyzed_rows),
        "profile_size_stats": {
            "min": min(technique_counts),
            "mean": round(statistics.mean(technique_counts), 2),
            "median": statistics.median(technique_counts),
            "max": max(technique_counts),
        },
        "distinguishable_count": len(finite_rows),
        "distinguishable_pct": round(len(finite_rows) / len(analyzed_rows) * 100, 1),
        "impossible_count": len(impossible_rows),
        "impossible_pct": round(len(impossible_rows) / len(analyzed_rows) * 100, 1),
        "witness_distribution": {
            str(size): count for size, count in sorted(witness_distribution.items())
        },
        "threshold_curve": build_threshold_curve(analyzed_rows),
        "rows": analyzed_rows,
    }

    if finite_sizes:
        summary["minimum_witness_stats"] = {
            "min": min(finite_sizes),
            "mean": round(statistics.mean(finite_sizes), 2),
            "median": statistics.median(finite_sizes),
            "max": max(finite_sizes),
            "max_overall_threshold_for_identifiable_profiles": max(finite_sizes),
            "identifiable_by_1_count": witness_distribution.get(1, 0),
            "identifiable_by_2_count": sum(
                count for size, count in witness_distribution.items() if size <= 2
            ),
            "identifiable_by_3_count": sum(
                count for size, count in witness_distribution.items() if size <= 3
            ),
            "identifiable_by_4_count": sum(
                count for size, count in witness_distribution.items() if size <= 4
            ),
        }
        summary["hardest_profiles"] = sorted(
            finite_rows,
            key=lambda row: (
                -int(row["min_witness_size"] or 0),
                -row["technique_count"],
                row["name"],
            ),
        )[:10]
    else:
        summary["minimum_witness_stats"] = None
        summary["hardest_profiles"] = []

    summary["impossible_profiles"] = sorted(
        impossible_rows,
        key=lambda row: (-row["blocker_count"], -row["technique_count"], row["name"]),
    )[:10]
    return summary


def compute_identifiability_report(bundle_path: Path) -> dict[str, Any]:
    objects, by_id = load_bundle(bundle_path)
    active_objects = [obj for obj in objects if is_active(obj)]
    relationships = [obj for obj in active_objects if obj.get("type") == "relationship"]
    forward_index = build_forward_index(relationships)

    campaigns = collect_profiles(objects, by_id, forward_index, "campaign")
    intrusion_sets = collect_profiles(objects, by_id, forward_index, "intrusion-set")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bundle_path": str(bundle_path),
        "methodology": {
            "task": (
                "Positive-evidence identifiability over ATT&CK technique profiles."
            ),
            "definition": (
                "A profile is distinguishable when there exists a subset of its "
                "techniques such that no other profile in the same corpus contains "
                "all techniques in that subset."
            ),
            "impossible_case": (
                "A profile is impossible to distinguish by positive technique "
                "evidence alone when some other profile subsumes it, i.e., contains "
                "every technique assigned to the focal profile."
            ),
            "minimum_witness": (
                "The minimum witness is the smallest distinguishing subset of "
                "techniques for a profile under the positive-evidence model."
            ),
        },
        "campaigns": summarize_profiles("campaign", campaigns, by_id),
        "intrusion_sets": summarize_profiles("intrusion-set", intrusion_sets, by_id),
    }


def write_report_files(report: dict[str, Any]) -> None:
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Paper 1 Identifiability Provenance",
        "",
        "Positive-evidence identifiability over ATT&CK profile technique sets.",
        "",
        "Definitions:",
        "- A profile is `distinguishable` when some subset of its techniques excludes every other profile in the same corpus.",
        "- A profile is `impossible` when another profile subsumes it.",
        "- `Minimum witness size` is the smallest distinguishing subset size.",
        "",
    ]

    for key in ("campaigns", "intrusion_sets"):
        section = report[key]
        witness_stats = section["minimum_witness_stats"]
        lines.extend(
            [
                f"## {section['label'].replace('_', ' ').title()}",
                "",
                f"- Profiles analyzed: `{section['profile_count']}`",
                f"- Distinguishable: `{section['distinguishable_count']}` (`{section['distinguishable_pct']}%`)",
                f"- Impossible under positive evidence alone: `{section['impossible_count']}` (`{section['impossible_pct']}%`)",
                f"- Technique count min/mean/median/max: `{section['profile_size_stats']['min']}` / `{section['profile_size_stats']['mean']}` / `{section['profile_size_stats']['median']}` / `{section['profile_size_stats']['max']}`",
            ]
        )
        if witness_stats is not None:
            lines.extend(
                [
                    f"- Minimum witness min/mean/median/max: `{witness_stats['min']}` / `{witness_stats['mean']}` / `{witness_stats['median']}` / `{witness_stats['max']}`",
                    f"- Witness distribution: `{section['witness_distribution']}`",
                    "",
                    "Hardest profiles:",
                ]
            )
            for row in section["hardest_profiles"]:
                lines.append(
                    f"- `{row['name']}`: witness `{row['min_witness_size']}`, "
                    f"profile size `{row['technique_count']}`, "
                    f"witness techniques `{row['witness_technique_ids']}`"
                )
        if section["impossible_profiles"]:
            lines.extend(["", "Sample impossible profiles:"])
            for row in section["impossible_profiles"]:
                sample_blockers = row["blocker_names"][:3]
                lines.append(
                    f"- `{row['name']}`: blocked by `{row['blocker_count']}` supersets, "
                    f"sample blockers `{sample_blockers}`"
                )
        lines.append("")

    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    args = parser.parse_args()

    report = compute_identifiability_report(args.bundle)
    write_report_files(report)

    campaigns = report["campaigns"]
    intrusion_sets = report["intrusion_sets"]
    print("Paper 1 identifiability report generated:")
    print(
        f"  campaigns      : {campaigns['distinguishable_count']}/{campaigns['profile_count']} distinguishable"
    )
    print(
        f"  intrusion-sets : {intrusion_sets['distinguishable_count']}/{intrusion_sets['profile_count']} distinguishable"
    )
    print(f"  json           : {OUTPUT_JSON}")
    print(f"  markdown       : {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
