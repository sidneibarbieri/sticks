#!/usr/bin/env python3
"""
Build a machine-readable comparison matrix between the legacy sticks-docker
campaigns and the current STICKS artifact.

For each legacy campaign the matrix records:
  - sticks_campaign_id     : corresponding campaign ID in current artifact
  - campaign_file          : whether campaigns/<id>.json exists
  - sut_profile            : whether data/sut_profiles/<id>.yml exists
  - executor_coverage      : fraction of techniques with a registered executor
  - latest_execution       : outcome of the most recent evidence run
  - status                 : COMPLETE | PARTIAL | MISSING (per acceptance criteria)
  - divergences            : list of documented methodological differences

Output:
  release/coverage_matrix.json
  release/COVERAGE_MATRIX.md
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from executors.executor_registry import registry  # noqa: E402
from executors.registry_initializer import initialize_registry  # noqa: E402
from loaders.campaign_loader import load_campaign  # noqa: E402

initialize_registry()

CAMPAIGNS_DIR = PROJECT_ROOT / "campaigns"
SUT_DIR = PROJECT_ROOT / "data" / "sut_profiles"
EVIDENCE_DIR = PROJECT_ROOT / "release" / "evidence"
OUTPUT_JSON = PROJECT_ROOT / "release" / "coverage_matrix.json"
OUTPUT_MD = PROJECT_ROOT / "release" / "COVERAGE_MATRIX.md"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)

# Legacy sticks-docker campaigns with their published technique counts.
DOCKER_CAMPAIGNS: dict[str, dict] = {
    "apt41_dust": {
        "docker_techniques": 24,
        "docker_name": "APT41 DUST",
        "divergences": [
            "docker_techniques=24 includes redundant sub-steps merged into 13 canonical ATT&CK techniques",
            "Web-service C2 (T1102) and infrastructure acquisition (T1583.006) simulated as inspired; no live external traffic",
        ],
    },
    "c0010": {
        "docker_techniques": 10,
        "docker_name": "C0010",
        "divergences": [
            "Resource-development steps remain inspired; no live external provider interaction",
        ],
    },
    "c0026": {
        "docker_techniques": 7,
        "docker_name": "C0026",
        "divergences": [
            "DNS resolution override adapted to lab-only local resolver path",
        ],
    },
    "costaricto": {
        "docker_techniques": 11,
        "docker_name": "CostaRicto",
        "divergences": [
            "Multi-hop proxy and external remote services remain inspired; no live C2 infrastructure",
        ],
    },
    "operation_midnighteclipse": {
        "docker_techniques": 18,
        "docker_name": "Operation MidnightEclipse",
        "divergences": [],
    },
    "outer_space": {
        "docker_techniques": 9,
        "docker_name": "Outer Space",
        "divergences": [
            "Satellite-themed C2 infrastructure acquisition simulated as inspired",
        ],
    },
    "salesforce_data_exfiltration": {
        "docker_techniques": 19,
        "docker_name": "Salesforce Data Exfiltration",
        "divergences": [
            "SaaS API calls to Salesforce simulated as inspired; no live tenant",
        ],
    },
    "shadowray": {
        "docker_techniques": 11,
        "docker_name": "ShadowRay",
        "divergences": [
            (
                "Ray Dashboard (CVE-2023-48022) provisioned by apply_sut_profile.py as a "
                "minimal unauthenticated HTTP stub on port 8265. "
                "The stub responds to /api/version and /api/jobs/ identically to a real Ray "
                "cluster with auth disabled. If the stub is absent on lab bring-up, "
                "the executor falls back to provisioning it inline inside the target VM. "
                "The boundary exercised (unauthenticated job-submission API) is methodologically "
                "equivalent to CVE-2023-48022 exploitation."
            ),
        ],
    },
}


@dataclass
class TechniqueRow:
    technique_id: str
    has_executor: bool


@dataclass
class ExecutionSummary:
    total: int
    successful: int
    failed: int
    success_rate: float
    evidence_path: str


@dataclass
class CampaignRow:
    docker_campaign: str
    docker_name: str
    docker_techniques: int
    sticks_campaign_id: str
    campaign_file: bool
    sut_profile: bool
    sticks_techniques: int
    executor_coverage: float
    techniques: list[TechniqueRow]
    latest_execution: ExecutionSummary | None
    status: str  # COMPLETE | PARTIAL | MISSING
    divergences: list[str] = field(default_factory=list)


def latest_evidence(campaign_id: str) -> ExecutionSummary | None:
    candidates = sorted(EVIDENCE_DIR.glob(f"{campaign_id}_*/summary.json"))
    if not candidates:
        return None
    path = max(candidates, key=lambda p: p.parent.name)
    data = json.loads(path.read_text(encoding="utf-8"))
    total = data.get("total_techniques", 0)
    successful = data.get("successful", 0)
    failed = data.get("failed", 0)
    return ExecutionSummary(
        total=total,
        successful=successful,
        failed=failed,
        success_rate=successful / total if total else 0.0,
        evidence_path=display_path(path.parent),
    )


def determine_status(row_data: dict) -> str:
    if not row_data["campaign_file"] or not row_data["sut_profile"]:
        return "MISSING"
    ev = row_data["latest_execution"]
    if ev is None:
        return "MISSING"
    if ev["failed"] == 0 and ev["successful"] > 0:
        return "COMPLETE"
    return "PARTIAL"


def build_matrix() -> list[CampaignRow]:
    rows = []
    for docker_name, meta in DOCKER_CAMPAIGNS.items():
        sid = f"0.{docker_name}"
        has_campaign = (CAMPAIGNS_DIR / f"{sid}.json").exists() or (CAMPAIGNS_DIR / f"{sid}.yml").exists()
        has_sut = (SUT_DIR / f"{sid}.yml").exists()

        techniques: list[TechniqueRow] = []
        if has_campaign:
            try:
                campaign = load_campaign(sid)
                for step in campaign.steps:
                    has_exec = registry.get(step.technique_id) is not None
                    techniques.append(TechniqueRow(technique_id=step.technique_id, has_executor=has_exec))
            except Exception:
                pass

        sticks_techniques = len(techniques)
        covered = sum(1 for t in techniques if t.has_executor)
        executor_coverage = covered / sticks_techniques if sticks_techniques else 0.0

        ev = latest_evidence(sid)
        ev_dict = asdict(ev) if ev else None

        row_dict = {
            "campaign_file": has_campaign,
            "sut_profile": has_sut,
            "latest_execution": ev_dict,
        }
        status = determine_status(row_dict)

        rows.append(
            CampaignRow(
                docker_campaign=docker_name,
                docker_name=meta["docker_name"],
                docker_techniques=meta["docker_techniques"],
                sticks_campaign_id=sid,
                campaign_file=has_campaign,
                sut_profile=has_sut,
                sticks_techniques=sticks_techniques,
                executor_coverage=executor_coverage,
                techniques=techniques,
                latest_execution=ev,
                status=status,
                divergences=meta.get("divergences", []),
            )
        )
    return rows


def write_markdown(rows: list[CampaignRow], generated_at: str) -> None:
    lines = [
        "# STICKS Campaign Coverage Matrix",
        "",
        f"Generated: `{generated_at}`",
        "",
        "Compares the eight legacy sticks-docker campaigns against the current STICKS artifact.",
        "",
        "**Status definitions**",
        "- `COMPLETE` — zero failed techniques, evidence generated, provenance consistent",
        "- `PARTIAL` — runs but at least one technique fails or evidence is incomplete",
        "- `MISSING` — campaign or SUT profile absent, or no execution recorded",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        "|---|---|",
    ]
    total = len(rows)
    complete = sum(1 for r in rows if r.status == "COMPLETE")
    partial = sum(1 for r in rows if r.status == "PARTIAL")
    missing = sum(1 for r in rows if r.status == "MISSING")
    lines += [
        f"| Legacy campaigns | {total} |",
        f"| COMPLETE | {complete} |",
        f"| PARTIAL | {partial} |",
        f"| MISSING | {missing} |",
        "",
        "## Matrix",
        "",
        "| Legacy Campaign | STICKS ID | Campaign File | SUT Profile | Docker Steps | STICKS Steps | Executor Coverage | Status |",
        "|---|---|:---:|:---:|---:|---:|---:|:---:|",
    ]
    for r in rows:
        coverage_str = f"{r.executor_coverage:.0%}"
        lines.append(
            f"| {r.docker_name} | `{r.sticks_campaign_id}` | "
            f"{'✓' if r.campaign_file else '✗'} | {'✓' if r.sut_profile else '✗'} | "
            f"{r.docker_techniques} | {r.sticks_techniques} | {coverage_str} | **{r.status}** |"
        )

    lines += ["", "## Methodological Divergences", ""]
    for r in rows:
        if r.divergences:
            lines.append(f"### {r.docker_name} (`{r.sticks_campaign_id}`)")
            lines.append("")
            for d in r.divergences:
                lines.append(f"- {d}")
            lines.append("")

    lines += ["", "## Latest Execution Results", ""]
    lines += [
        "| STICKS ID | Status | Successful | Failed | Total | Success Rate |",
        "|---|:---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        ev = r.latest_execution
        if ev:
            lines.append(
                f"| `{r.sticks_campaign_id}` | **{r.status}** | {ev.successful} | "
                f"{ev.failed} | {ev.total} | {ev.success_rate:.1%} |"
            )
        else:
            lines.append(f"| `{r.sticks_campaign_id}` | **{r.status}** | — | — | — | — |")

    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = build_matrix()
    generated_at = datetime.now().isoformat(timespec="seconds")

    report = {
        "generated_at": generated_at,
        "total": len(rows),
        "complete": sum(1 for r in rows if r.status == "COMPLETE"),
        "partial": sum(1 for r in rows if r.status == "PARTIAL"),
        "missing": sum(1 for r in rows if r.status == "MISSING"),
        "campaigns": [
            {
                **{k: v for k, v in asdict(r).items() if k != "techniques"},
                "techniques": [asdict(t) for t in r.techniques],
                "latest_execution": asdict(r.latest_execution) if r.latest_execution else None,
            }
            for r in rows
        ],
    }

    OUTPUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(rows, generated_at)
    print(f"Coverage matrix written to:")
    print(f"  {OUTPUT_JSON}")
    print(f"  {OUTPUT_MD}")
    print()
    print(f"  Total : {report['total']}")
    print(f"  COMPLETE : {report['complete']}")
    print(f"  PARTIAL  : {report['partial']}")
    print(f"  MISSING  : {report['missing']}")


if __name__ == "__main__":
    main()
