#!/usr/bin/env python3
"""
Generate paper-facing measurements that compare the legacy sticks-docker corpus
with the current STICKS corpus and execution state.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
DOCKER_DAG_DIR = REPO_ROOT / "sticks-docker" / "sticks" / "data" / "dag"
CAMPAIGNS_DIR = PROJECT_ROOT / "campaigns"
SUT_DIR = PROJECT_ROOT / "data" / "sut_profiles"
EVIDENCE_DIR = PROJECT_ROOT / "release" / "evidence"
LEGACY_PARITY = PROJECT_ROOT / "results" / "legacy_parity_report.json"
MITRE_AUDIT = PROJECT_ROOT / "results" / "mitre_metadata_audit.json"
HOST_LEAKAGE = PROJECT_ROOT / "results" / "host_leakage_audit.json"
OUTPUT_JSON = PROJECT_ROOT / "results" / "paper_measurements.json"
OUTPUT_MD = PROJECT_ROOT / "results" / "PAPER_MEASUREMENTS.md"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def latest_summary(campaign_id: str) -> dict | None:
    candidates = sorted(EVIDENCE_DIR.glob(f"{campaign_id}_*/summary.json"))
    if not candidates:
        return None
    latest = max(candidates, key=lambda path: path.parent.name)
    summary = json.loads(latest.read_text(encoding="utf-8"))
    total = summary.get("total_techniques", 0)
    successful = summary.get("successful", 0)
    failed = summary.get("failed", 0)
    return {
        "summary_path": str(latest),
        "total_techniques": total,
        "successful": successful,
        "failed": failed,
        "success_rate": successful / total if total else 0.0,
    }


def build_report() -> dict:
    docker_campaigns = sorted(
        path.stem.replace("_dag", "") for path in DOCKER_DAG_DIR.glob("*_dag.json")
    )
    published = sorted(path.stem for path in CAMPAIGNS_DIR.glob("*.json"))
    sut_profiles = {path.stem for path in SUT_DIR.glob("*.yml")}

    parity = load_json(LEGACY_PARITY)
    mitre = load_json(MITRE_AUDIT)
    host_leakage = load_json(HOST_LEAKAGE)
    parity_by_campaign = {
        item["sticks_campaign"]: item for item in parity.get("campaigns", [])
    }
    leakage_by_campaign = {
        item["campaign_id"]: item for item in host_leakage.get("campaigns", [])
    }
    mitre_by_campaign = {
        item["campaign_id"]: item for item in mitre.get("campaigns", [])
    }

    rows = []
    for docker_campaign in docker_campaigns:
        sticks_campaign = f"0.{docker_campaign}"
        parity_row = parity_by_campaign.get(sticks_campaign)
        summary = latest_summary(sticks_campaign) if sticks_campaign in published else None
        mitre_row = mitre_by_campaign.get(sticks_campaign, {})
        leakage_row = leakage_by_campaign.get(sticks_campaign, {})
        rows.append(
            {
                "docker_campaign": docker_campaign,
                "sticks_campaign": sticks_campaign,
                "published": sticks_campaign in published,
                "has_sut": sticks_campaign in sut_profiles,
                "legacy_exact_match": bool(
                    parity_row and parity_row.get("exact_technique_match")
                ),
                "legacy_coverage_rate": (
                    parity_row.get("legacy_coverage_rate", 0.0) if parity_row else 0.0
                ),
                "latest_execution": summary,
                "mitre_metadata_clean": (
                    mitre_row.get("steps_with_missing_metadata", 1) == 0
                    and mitre_row.get("steps_with_tactic_mismatch", 1) == 0
                    and mitre_row.get("steps_without_mitre_support", 1) == 0
                ),
                "host_leakage_detected": bool(
                    leakage_row.get("host_leakage_detected", False)
                ),
            }
        )

    executable_legacy = [row for row in rows if row["has_sut"]]
    clean_legacy = [
        row
        for row in rows
        if row["latest_execution"] and row["latest_execution"]["failed"] == 0
    ]
    leak_free_legacy = [row for row in rows if not row["host_leakage_detected"]]

    return {
        "generated_at": datetime.now().isoformat(),
        "legacy_campaigns_total": len(docker_campaigns),
        "legacy_campaigns_published_in_sticks": sum(1 for row in rows if row["published"]),
        "legacy_campaigns_with_sut": len(executable_legacy),
        "legacy_campaigns_with_zero_failed_latest_execution": len(clean_legacy),
        "legacy_campaigns_without_host_leakage": len(leak_free_legacy),
        "legacy_exact_technique_matches": [
            row["sticks_campaign"] for row in rows if row["legacy_exact_match"]
        ],
        "legacy_technique_coverage_rate": parity.get(
            "legacy_technique_coverage_rate", 0.0
        ),
        "rows": rows,
    }


def write_markdown(report: dict) -> None:
    lines = [
        "# Paper Measurements",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Legacy campaigns in sticks-docker: `{report['legacy_campaigns_total']}`",
        f"- Legacy campaigns published in STICKS: `{report['legacy_campaigns_published_in_sticks']}`",
        f"- Legacy campaigns with SUT profile: `{report['legacy_campaigns_with_sut']}`",
        f"- Legacy campaigns with zero failed techniques in latest execution: `{report['legacy_campaigns_with_zero_failed_latest_execution']}`",
        f"- Legacy campaigns without host leakage in latest evidence: `{report['legacy_campaigns_without_host_leakage']}`",
        f"- Legacy technique coverage rate: `{report['legacy_technique_coverage_rate']:.1%}`",
        f"- Legacy exact technique matches: `{', '.join(report['legacy_exact_technique_matches']) or 'none'}`",
        "",
        "## Legacy Campaign Matrix",
        "",
        "| Docker | STICKS | Published | SUT | Exact Match | Legacy Coverage | Latest Success | MITRE Clean | Host Leakage |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in report["rows"]:
        latest = row["latest_execution"]
        latest_text = (
            f"{latest['successful']}/{latest['total_techniques']} ({latest['success_rate']:.1%})"
            if latest
            else "none"
        )
        lines.append(
            f"| {row['docker_campaign']} | {row['sticks_campaign']} | "
            f"{'yes' if row['published'] else 'no'} | "
            f"{'yes' if row['has_sut'] else 'no'} | "
            f"{'yes' if row['legacy_exact_match'] else 'no'} | "
            f"{row['legacy_coverage_rate']:.1%} | "
            f"{latest_text} | "
            f"{'yes' if row['mitre_metadata_clean'] else 'no'} | "
            f"{'yes' if row['host_leakage_detected'] else 'no'} |"
        )

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    report = build_report()
    OUTPUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
