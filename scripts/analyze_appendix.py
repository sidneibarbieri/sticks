#!/usr/bin/env python3
"""
Generate Paper 1 appendix provenance from bundle and STICKS execution evidence.

Produces:
- Field population statistics for automation-relevant STIX fields
- Non-sequential campaign itemset support analysis
- STICKS execution breakdown (replaces Docker execution in the sticks-docker version)
"""

from __future__ import annotations

import itertools
import json
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENTERPRISE_BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"
EVIDENCE_DIR = PROJECT_ROOT / "release" / "evidence"
PROVENANCE_JSON = PROJECT_ROOT / "results" / "paper1_appendix_provenance.json"
PROVENANCE_MD = PROJECT_ROOT / "results" / "PAPER1_APPENDIX_PROVENANCE.md"
CAMPAIGNS_DIR = PROJECT_ROOT / "campaigns"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def active_attack_patterns(bundle: dict) -> list[dict]:
    out = []
    for obj in bundle["objects"]:
        if obj.get("type") != "attack-pattern":
            continue
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue
        ext_ids = [
            ref.get("external_id", "")
            for ref in obj.get("external_references", [])
            if ref.get("source_name") == "mitre-attack"
        ]
        if any(ext.startswith("T") for ext in ext_ids):
            out.append(obj)
    return out


def nonempty(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(nonempty(v) for v in value)
    return True


def field_population(attack_patterns: list[dict]) -> dict[str, dict[str, int]]:
    fields = [
        "kill_chain_phases",
        "x_mitre_platforms",
        "x_mitre_system_requirements",
        "x_mitre_detection",
        "x_mitre_data_sources",
        "x_mitre_permissions_required",
    ]
    stats = {}
    for field in fields:
        present = sum(1 for obj in attack_patterns if field in obj)
        non_empty = sum(1 for obj in attack_patterns if nonempty(obj.get(field)))
        stats[field] = {"present": present, "non_empty": non_empty}
    return stats


def campaign_sets(bundle: dict) -> list[list[str]]:
    tech_ids = {}
    for obj in active_attack_patterns(bundle):
        ext_id = next(
            ref["external_id"]
            for ref in obj.get("external_references", [])
            if ref.get("source_name") == "mitre-attack"
            and ref.get("external_id", "").startswith("T")
        )
        tech_ids[obj["id"]] = ext_id

    campaigns = {
        obj["id"]: obj.get("name")
        for obj in bundle["objects"]
        if obj.get("type") == "campaign"
        and not obj.get("revoked")
        and not obj.get("x_mitre_deprecated")
    }
    rels = [
        obj
        for obj in bundle["objects"]
        if obj.get("type") == "relationship"
        and obj.get("relationship_type") == "uses"
        and not obj.get("revoked")
        and not obj.get("x_mitre_deprecated")
    ]

    campaign_techniques: list[list[str]] = []
    for campaign_id in campaigns:
        techniques = sorted(
            {
                tech_ids[rel["target_ref"]]
                for rel in rels
                if rel.get("source_ref") == campaign_id
                and rel.get("target_ref") in tech_ids
            }
        )
        if techniques:
            campaign_techniques.append(techniques)
    return campaign_techniques


def itemset_support(
    campaigns: list[list[str]], max_size: int = 5,
) -> list[dict[str, float | int]]:
    out = []
    total = len(campaigns)
    for size in range(1, max_size + 1):
        counter: Counter[tuple[str, ...]] = Counter()
        for techniques in campaigns:
            if len(techniques) >= size:
                counter.update(itertools.combinations(techniques, size))
        top_itemset, top_support = counter.most_common(1)[0]
        out.append(
            {
                "size": size,
                "max_support": top_support,
                "fraction_pct": round(100.0 * top_support / total, 1),
                "itemset": list(top_itemset),
            }
        )
    return out


def get_latest_summary(campaign_id: str) -> dict | None:
    campaign_dirs = [
        d
        for d in EVIDENCE_DIR.glob(f"{campaign_id}_*")
        if d.name[len(campaign_id) + 1 : len(campaign_id) + 9].isdigit()
    ]
    if not campaign_dirs:
        return None
    latest_dir = max(campaign_dirs, key=lambda path: path.name)
    summary_path = latest_dir / "summary.json"
    if not summary_path.exists():
        return None
    return json.loads(summary_path.read_text())


def sticks_execution_breakdown() -> list[dict]:
    published = sorted(
        path.stem
        for path in CAMPAIGNS_DIR.glob("*.json")
        if not path.name.startswith("_")
    )
    rows = []
    for campaign_id in published:
        summary = get_latest_summary(campaign_id)
        if summary is None:
            continue
        rows.append(
            {
                "campaign": campaign_id,
                "total_techniques": summary["total_techniques"],
                "successful": summary["successful"],
                "failed": summary.get("failed", 0),
                "success_rate": round(
                    100.0 * summary["successful"] / summary["total_techniques"], 1,
                )
                if summary["total_techniques"]
                else 0.0,
                "infrastructure_provider": summary.get("infrastructure_provider", ""),
            }
        )
    return rows


def write_provenance(
    field_stats: dict,
    itemsets: list[dict],
    execution_rows: list[dict],
    total_attack_patterns: int,
) -> None:
    payload = {
        "bundle": str(ENTERPRISE_BUNDLE),
        "active_attack_patterns": total_attack_patterns,
        "field_population": field_stats,
        "itemset_support": itemsets,
        "sticks_execution_breakdown": execution_rows,
    }
    PROVENANCE_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE_JSON.write_text(json.dumps(payload, indent=2))

    lines = [
        "# Paper 1 Appendix Provenance",
        "",
        f"- Bundle: `{ENTERPRISE_BUNDLE}`",
        f"- Active Enterprise attack-patterns: `{total_attack_patterns}`",
        "",
        "## Automation-Relevant Field Population",
        "",
    ]
    for field, stats in field_stats.items():
        lines.append(
            f"- `{field}`: present `{stats['present']}`, non-empty `{stats['non_empty']}`"
        )
    lines.extend(
        [
            "",
            "## Non-Sequential Campaign Itemset Support",
            "",
        ]
    )
    for row in itemsets:
        lines.append(
            f"- Size `{row['size']}`: max support `{row['max_support']}` "
            f"({row['fraction_pct']:.1f}%), example `{', '.join(row['itemset'])}`"
        )
    lines.extend(
        [
            "",
            "## STICKS Execution Breakdown",
            "",
        ]
    )
    for row in execution_rows:
        lines.append(
            f"- `{row['campaign']}`: {row['successful']}/{row['total_techniques']} "
            f"({row['success_rate']:.1f}%), infra=`{row['infrastructure_provider']}`"
        )
    PROVENANCE_MD.write_text("\n".join(lines) + "\n")


def main() -> None:
    bundle = load_json(ENTERPRISE_BUNDLE)
    attack_patterns = active_attack_patterns(bundle)
    field_stats = field_population(attack_patterns)
    itemsets = itemset_support(campaign_sets(bundle))
    execution_rows = sticks_execution_breakdown()
    write_provenance(field_stats, itemsets, execution_rows, len(attack_patterns))
    print(f"Wrote {PROVENANCE_JSON}")
    print(f"Wrote {PROVENANCE_MD}")


if __name__ == "__main__":
    main()
