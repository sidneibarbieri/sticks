#!/usr/bin/env python3
"""
Audit parity between sticks-docker campaigns and the current published STICKS corpus.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
DOCKER_DAG_DIR = REPO_ROOT / "sticks-docker" / "sticks" / "data" / "dag"
PUBLISHED_CAMPAIGNS_DIR = PROJECT_ROOT / "campaigns"
SUT_PROFILES_DIR = PROJECT_ROOT / "data" / "sut_profiles"
CANONICAL_EVIDENCE_DIR = PROJECT_ROOT / "release" / "evidence"
OUTPUT_JSON = PROJECT_ROOT / "results" / "legacy_parity_report.json"
OUTPUT_MD = PROJECT_ROOT / "results" / "LEGACY_PARITY_REPORT.md"

sys.path.insert(0, str(PROJECT_ROOT / "src"))
from executors.executor_registry import registry  # noqa: E402
from executors.registry_initializer import initialize_registry  # noqa: E402


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


@dataclass
class CampaignParity:
    docker_campaign: str
    sticks_campaign: str
    docker_techniques: int
    sticks_techniques: int
    common_techniques: int
    legacy_coverage_rate: float
    exact_technique_match: bool
    docker_only: list[str]
    sticks_only: list[str]
    sut_profile_present: bool
    docker_only_with_executor: list[str]
    docker_only_without_executor: list[str]
    migration_readiness: str
    latest_execution: dict | None


def load_docker_techniques(path: Path) -> list[str]:
    data = json.loads(path.read_text())
    return [
        node["technique_id"]
        for node in data.get("structural_nodes", [])
        if node.get("technique_id")
    ]


def load_sticks_techniques(path: Path) -> list[str]:
    data = json.loads(path.read_text())
    return [
        node["technique_id"]
        for node in data.get("techniques", [])
        if node.get("technique_id")
    ]


def latest_summary(campaign_id: str) -> dict | None:
    candidates = sorted(CANONICAL_EVIDENCE_DIR.glob(f"{campaign_id}_*/summary.json"))
    if not candidates:
        return None
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    data = json.loads(latest.read_text())
    return {
        "evidence_dir": display_path(latest.parent),
        "successful": data.get("successful", 0),
        "failed": data.get("failed", 0),
        "total_techniques": data.get("total_techniques", 0),
        "success_rate": (
            data.get("successful", 0) / max(data.get("total_techniques", 1), 1)
        ),
    }


def build_report() -> dict:
    parity_rows: list[CampaignParity] = []
    docker_campaigns = sorted(DOCKER_DAG_DIR.glob("*_dag.json"))
    initialize_registry(force=True)
    available_executors = set(registry.list_available())

    for docker_path in docker_campaigns:
        docker_campaign = docker_path.stem.replace("_dag", "")
        sticks_campaign = f"0.{docker_campaign}"
        sticks_path = PUBLISHED_CAMPAIGNS_DIR / f"{sticks_campaign}.json"
        if not sticks_path.exists():
            continue

        docker_techniques = load_docker_techniques(docker_path)
        sticks_techniques = load_sticks_techniques(sticks_path)
        common = sorted(set(docker_techniques) & set(sticks_techniques))
        docker_only = sorted(set(docker_techniques) - set(sticks_techniques))
        sticks_only = sorted(set(sticks_techniques) - set(docker_techniques))
        docker_only_with_executor = sorted(
            technique_id
            for technique_id in docker_only
            if technique_id in available_executors
        )
        docker_only_without_executor = sorted(
            technique_id
            for technique_id in docker_only
            if technique_id not in available_executors
        )
        sut_profile_present = (SUT_PROFILES_DIR / f"{sticks_campaign}.yml").exists()
        if set(docker_techniques) == set(sticks_techniques):
            migration_readiness = "exact_match"
        elif docker_only_without_executor:
            migration_readiness = "executor_gap"
        elif not sut_profile_present:
            migration_readiness = "missing_sut"
        else:
            migration_readiness = "campaign_alignment"

        parity_rows.append(
            CampaignParity(
                docker_campaign=docker_campaign,
                sticks_campaign=sticks_campaign,
                docker_techniques=len(docker_techniques),
                sticks_techniques=len(sticks_techniques),
                common_techniques=len(common),
                legacy_coverage_rate=(
                    len(common) / len(set(docker_techniques)) if docker_techniques else 0
                ),
                exact_technique_match=(
                    set(docker_techniques) == set(sticks_techniques)
                ),
                docker_only=docker_only,
                sticks_only=sticks_only,
                sut_profile_present=sut_profile_present,
                docker_only_with_executor=docker_only_with_executor,
                docker_only_without_executor=docker_only_without_executor,
                migration_readiness=migration_readiness,
                latest_execution=latest_summary(sticks_campaign),
            )
        )

    total_docker = set()
    total_sticks_overlap = set()
    for row in parity_rows:
        total_docker.update(row.docker_only)
        total_docker.update(row.sticks_only)

    docker_technique_universe = set()
    matched_techniques = set()
    for docker_path in docker_campaigns:
        docker_technique_universe.update(load_docker_techniques(docker_path))
        sticks_campaign = PUBLISHED_CAMPAIGNS_DIR / f"0.{docker_path.stem.replace('_dag', '')}.json"
        if sticks_campaign.exists():
            matched_techniques.update(
                set(load_docker_techniques(docker_path))
                & set(load_sticks_techniques(sticks_campaign))
            )

    return {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "docker_campaign_count": len(docker_campaigns),
        "published_campaign_count": len(
            list(PUBLISHED_CAMPAIGNS_DIR.glob("*.json"))
        ),
        "mapped_legacy_campaigns": len(parity_rows),
        "docker_technique_universe": len(docker_technique_universe),
        "matched_docker_techniques": len(matched_techniques),
        "legacy_technique_coverage_rate": (
            len(matched_techniques) / len(docker_technique_universe)
            if docker_technique_universe
            else 0
        ),
        "available_executor_count": len(available_executors),
        "mapped_campaigns_with_sut_profile": sum(
            1 for row in parity_rows if row.sut_profile_present
        ),
        "legacy_docker_only_with_executor": len(
            {
                technique_id
                for row in parity_rows
                for technique_id in row.docker_only_with_executor
            }
        ),
        "legacy_docker_only_without_executor": len(
            {
                technique_id
                for row in parity_rows
                for technique_id in row.docker_only_without_executor
            }
        ),
        "exact_technique_matches": [
            row.sticks_campaign for row in parity_rows if row.exact_technique_match
        ],
        "campaigns": [asdict(row) for row in parity_rows],
    }


def write_markdown(report: dict) -> None:
    lines = [
        "# Legacy Parity Audit",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Docker campaigns: `{report['docker_campaign_count']}`",
        f"- Published STICKS campaigns: `{report['published_campaign_count']}`",
        f"- Legacy campaigns with direct published counterpart: `{report['mapped_legacy_campaigns']}`",
        f"- Docker technique universe: `{report['docker_technique_universe']}`",
        f"- Matched Docker techniques in published corpus: `{report['matched_docker_techniques']}`",
        f"- Legacy technique coverage rate: `{report['legacy_technique_coverage_rate']:.1%}`",
        f"- Available executors in registry: `{report['available_executor_count']}`",
        f"- Mapped legacy campaigns with SUT profile: `{report['mapped_campaigns_with_sut_profile']}`",
        f"- Docker-only legacy techniques already covered by current executors: `{report['legacy_docker_only_with_executor']}`",
        f"- Docker-only legacy techniques still missing executor coverage: `{report['legacy_docker_only_without_executor']}`",
        "",
        "## Exact Technique Matches",
        "",
    ]

    exact = report["exact_technique_matches"]
    if exact:
        lines.extend(f"- `{campaign_id}`" for campaign_id in exact)
    else:
        lines.append("- None")

    lines.extend(["", "## Campaign-Level Audit", ""])
    for campaign in report["campaigns"]:
        lines.extend(
            [
                f"### {campaign['sticks_campaign']}",
                "",
                f"- Docker source: `{campaign['docker_campaign']}`",
                f"- Docker techniques: `{campaign['docker_techniques']}`",
                f"- STICKS techniques: `{campaign['sticks_techniques']}`",
                f"- Common techniques: `{campaign['common_techniques']}`",
                f"- Legacy coverage rate: `{campaign['legacy_coverage_rate']:.1%}`",
                f"- Exact technique match: `{campaign['exact_technique_match']}`",
                f"- SUT profile present: `{campaign['sut_profile_present']}`",
                f"- Migration readiness: `{campaign['migration_readiness']}`",
                f"- Docker-only techniques: `{', '.join(campaign['docker_only']) or 'none'}`",
                f"- Docker-only techniques with executor already available: `{', '.join(campaign['docker_only_with_executor']) or 'none'}`",
                f"- Docker-only techniques missing executor coverage: `{', '.join(campaign['docker_only_without_executor']) or 'none'}`",
                f"- STICKS-only techniques: `{', '.join(campaign['sticks_only']) or 'none'}`",
            ]
        )
        latest_execution = campaign["latest_execution"]
        if latest_execution:
            lines.append(
                "- Latest execution: "
                f"{latest_execution['successful']}/{latest_execution['total_techniques']} "
                f"({latest_execution['success_rate']:.1%})"
            )
        else:
            lines.append("- Latest execution: none")
        lines.append("")

    OUTPUT_MD.write_text("\n".join(lines))


def main() -> None:
    report = build_report()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, indent=2))
    write_markdown(report)
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
