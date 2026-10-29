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
  runs/legacy-coverage/coverage_matrix.json
  runs/legacy-coverage/COVERAGE_MATRIX.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from executors.executor_registry import registry  # noqa: E402
from executors.registry_initializer import initialize_registry  # noqa: E402
from loaders.campaign_loader import load_campaign  # noqa: E402
from concretization.legacy_dag_corpus import resolve_legacy_dag_dir  # noqa: E402

initialize_registry()

CAMPAIGNS_DIR = PROJECT_ROOT / "campaigns"
SUT_DIR = PROJECT_ROOT / "data" / "sut_profiles"
EVIDENCE_DIR = PROJECT_ROOT / "release" / "evidence"
TYPED_OUTCOMES_DIR = PROJECT_ROOT / "release" / "experiments" / "typed_campaign_outcomes"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "runs" / "legacy-coverage"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)

# Historical reported node counts include non-technique nodes.
DOCKER_CAMPAIGNS: dict[str, dict] = {
    "apt41_dust": {
        "docker_techniques": 24,
        "docker_name": "APT41 DUST",
        "divergences": [
            "Historical reported node count and retained technique count use different units",
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
                "Ray Dashboard (CVE-2023-48022) is exposed as a declared step-conditioned "
                "SUT overlay immediately before T1190, not hidden inside the base image. "
                "The overlay provisions a minimal unauthenticated HTTP stub on port 8265 "
                "that responds to /api/version and /api/jobs/ like a Ray cluster with "
                "auth disabled. If the overlay is absent, the executor still falls back "
                "to provisioning the same boundary inline inside the target VM. "
                "The GET probes observe a synthetic unauthenticated HTTP surface; they do not "
                "demonstrate Ray job submission, code execution, or CVE-2023-48022 exploitation."
            ),
        ],
    },
}


@dataclass
class TechniqueRow:
    technique_id: str
    has_executor: bool
    declared_execution_mode: str | None
    declared_fidelity: str | None


class ReceiptCounts(BaseModel):
    """Strict counters from a runner receipt, not observed-effect evidence."""

    model_config = ConfigDict(strict=True)

    total_techniques: int = Field(default=0, ge=0)
    successful: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)


class TypedOutcomeReceipt(BaseModel):
    """A bounded QEMU outcome receipt, distinct from a per-technique runner summary."""

    model_config = ConfigDict(strict=True, extra="ignore")

    campaign_id: str = Field(min_length=1)
    cycle_passed: bool
    scope: str = Field(min_length=1)
    source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    guest_effects_observed: int = Field(default=0, ge=0)
    controller_effects_observed: int = Field(default=0, ge=0)
    runner_effects_observed: int = Field(default=0, ge=0)
    simulated: int = Field(default=0, ge=0)
    runner_simulated: int = Field(default=0, ge=0)
    runner_total_techniques: int | None = Field(default=None, ge=0)


@dataclass
class ExecutionSummary:
    total: int
    successful: int
    failed: int
    success_rate: float
    evidence_path: str
    campaign_id: str | None
    sut_profile_id: str | None
    technique_ids: list[str | None]
    step_statuses: list[str | None]
    summary_sha256: str
    evidence_kind: str
    scope: str | None = None


@dataclass
class CampaignRow:
    docker_campaign: str
    docker_name: str
    docker_techniques: int
    historical_reported_nodes: int
    historical_inventory_sha256: str
    technique_occurrences_preserved: bool
    sticks_campaign_id: str
    campaign_file: bool
    sut_profile: bool
    sticks_techniques: int
    executor_coverage: float
    techniques: list[TechniqueRow]
    latest_execution: ExecutionSummary | None
    status: str  # COMPLETE | PARTIAL | MISSING
    divergences: list[str] = field(default_factory=list)


def _latest_runner_summary(
    campaign_id: str, *, evidence_dir: Path | None = None,
) -> ExecutionSummary | None:
    root = EVIDENCE_DIR if evidence_dir is None else evidence_dir
    if root.is_symlink():
        raise ValueError("Evidence directory must not be a symlink")
    if evidence_dir is None and not root.exists():
        return None
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    candidates = sorted(root.glob(f"{campaign_id}_*/summary.json"))
    if not candidates:
        return None
    path = max(candidates, key=lambda p: p.parent.name)
    if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("Evidence summary must not escape its directory through a symlink")
    summary_bytes = path.read_bytes()
    data = json.loads(summary_bytes)
    counts = ReceiptCounts.model_validate(data)
    total = counts.total_techniques
    successful = counts.successful
    failed = counts.failed
    return ExecutionSummary(
        total=total,
        successful=successful,
        failed=failed,
        success_rate=successful / total if total else 0.0,
        evidence_path=display_path(path.parent),
        campaign_id=data.get("campaign_id"),
        sut_profile_id=data.get("sut_profile_id"),
        technique_ids=[step.get("technique_id") for step in data.get("technique_results", [])],
        step_statuses=[step.get("status") for step in data.get("technique_results", [])],
        summary_sha256=hashlib.sha256(summary_bytes).hexdigest(),
        evidence_kind="runner_summary",
    )


def _typed_outcome_evidence(campaign_id: str) -> ExecutionSummary | None:
    if not TYPED_OUTCOMES_DIR.is_dir():
        return None
    receipt_name = f"{campaign_id.removeprefix('0.').upper()}.final_run_receipt.json"
    receipt_path = TYPED_OUTCOMES_DIR / receipt_name
    if not receipt_path.is_file():
        return None
    if receipt_path.is_symlink() or not receipt_path.resolve().is_relative_to(
        TYPED_OUTCOMES_DIR.resolve(strict=True)
    ):
        raise ValueError("typed outcome receipt must not escape its directory through a symlink")
    receipt_bytes = receipt_path.read_bytes()
    receipt = TypedOutcomeReceipt.model_validate_json(receipt_bytes)
    if receipt.campaign_id != campaign_id:
        raise ValueError("typed outcome receipt campaign does not match requested campaign")
    observed = (
        receipt.guest_effects_observed
        + receipt.controller_effects_observed
        + receipt.runner_effects_observed
    )
    simulated = receipt.simulated + receipt.runner_simulated
    total = receipt.runner_total_techniques if receipt.runner_total_techniques is not None else observed + simulated
    if observed + simulated > total:
        raise ValueError("typed outcome receipt counts exceed its declared total")
    return ExecutionSummary(
        total=total,
        successful=observed if receipt.cycle_passed else 0,
        failed=0 if receipt.cycle_passed else total,
        success_rate=observed / total if total else 0.0,
        evidence_path=display_path(receipt_path),
        campaign_id=receipt.campaign_id,
        sut_profile_id=None,
        technique_ids=[],
        step_statuses=[],
        summary_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
        evidence_kind="typed_outcome",
        scope=receipt.scope,
    )


def latest_evidence(
    campaign_id: str, *, evidence_dir: Path | None = None,
) -> ExecutionSummary | None:
    """Return a generic runner summary, or a bounded typed outcome for the default population.

    A typed outcome establishes observed effects in its declared scope. It is intentionally not a
    substitute for a complete per-technique runner summary and therefore can never yield COMPLETE.
    """
    runner_summary = _latest_runner_summary(campaign_id, evidence_dir=evidence_dir)
    if runner_summary is not None or evidence_dir is not None:
        return runner_summary
    return _typed_outcome_evidence(campaign_id)


def determine_status(row_data: dict) -> str:
    if not row_data["campaign_file"] or not row_data["sut_profile"]:
        return "MISSING"
    ev = row_data["latest_execution"]
    if ev is None:
        return "MISSING"
    expected_steps = row_data["sticks_techniques"]
    if any(type(ev.get(name)) is not int or ev[name] < 0 for name in ("total", "successful", "failed")):
        return "PARTIAL"
    if (
        ev.get("evidence_kind", "runner_summary") == "runner_summary"
        and expected_steps > 0
        and ev["failed"] == 0
        and ev["total"] == expected_steps
        and ev["successful"] == expected_steps
        and ev.get("campaign_id") == row_data["sticks_campaign_id"]
        and ev.get("sut_profile_id") == row_data["sticks_campaign_id"]
        and Counter(ev.get("technique_ids", [])) == Counter(row_data["expected_techniques"])
        and ev.get("step_statuses") == ["success"] * expected_steps
    ):
        return "COMPLETE"
    return "PARTIAL"


def build_matrix(*, evidence_dir: Path | None = None) -> list[CampaignRow]:
    rows = []
    legacy_dir = resolve_legacy_dag_dir(PROJECT_ROOT)
    for docker_name, meta in DOCKER_CAMPAIGNS.items():
        sid = f"0.{docker_name}"
        has_campaign = (CAMPAIGNS_DIR / f"{sid}.json").exists() or (CAMPAIGNS_DIR / f"{sid}.yml").exists()
        has_sut = (SUT_DIR / f"{sid}.yml").exists()
        legacy_path = legacy_dir / f"{docker_name}_dag.json"
        legacy_bytes = legacy_path.read_bytes()
        legacy = json.loads(legacy_bytes)
        legacy_techniques = [
            node["technique_id"] for node in legacy["structural_nodes"]
            if node.get("technique_id")
        ]

        techniques: list[TechniqueRow] = []
        if has_campaign:
            campaign = load_campaign(sid)
            for step in campaign.steps:
                has_executor = (
                    registry.get_executor(step.technique_id, sid) is not None
                )
                metadata = registry.get_metadata(step.technique_id, sid)
                techniques.append(
                    TechniqueRow(
                        technique_id=step.technique_id,
                        has_executor=has_executor,
                        declared_execution_mode=(metadata.execution_mode.value if metadata else None),
                        declared_fidelity=(metadata.execution_fidelity.value if metadata else None),
                    )
                )

        sticks_techniques = len(techniques)
        covered = sum(1 for t in techniques if t.has_executor)
        executor_coverage = covered / sticks_techniques if sticks_techniques else 0.0

        ev = latest_evidence(sid, evidence_dir=evidence_dir)
        ev_dict = asdict(ev) if ev else None

        row_dict = {
            "campaign_file": has_campaign,
            "sut_profile": has_sut,
            "sticks_techniques": sticks_techniques,
            "sticks_campaign_id": sid,
            "expected_techniques": [technique.technique_id for technique in techniques],
            "latest_execution": ev_dict,
        }
        status = determine_status(row_dict)

        rows.append(
            CampaignRow(
                docker_campaign=docker_name,
                docker_name=meta["docker_name"],
                docker_techniques=len(legacy_techniques),
                historical_reported_nodes=meta["docker_techniques"],
                historical_inventory_sha256=hashlib.sha256(legacy_bytes).hexdigest(),
                technique_occurrences_preserved=(
                    Counter(legacy_techniques) == Counter(t.technique_id for t in techniques)
                ),
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


def write_markdown(
    rows: list[CampaignRow],
    generated_at: str,
    output_path: Path,
) -> None:
    lines = [
        "# STICKS Campaign Coverage Matrix",
        "",
        f"Generated: `{generated_at}`",
        "",
        "Compares the eight legacy sticks-docker campaigns against the current STICKS artifact.",
        "",
        "**Status definitions**",
        "- `COMPLETE` - campaign and SUT IDs, technique multiplicities, totals and per-step successes match the current campaign",
        "- `PARTIAL` - execution counts differ from the campaign or failures are reported",
        "- `MISSING` - campaign or SUT profile absent, or no execution recorded",
        "",
        "Runner completeness does not certify causal ordering, independently observed effects, historical fidelity, or provenance integrity.",
        "Executor coverage counts registered callables, including simulations; declared modes and fidelity are metadata, not observed effects.",
        "Historical reported node counts and retained technique occurrences have different denominators. The JSON binds the retained inventory by SHA-256.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
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
            f"{'[ok]' if r.campaign_file else '[fail]'} | {'[ok]' if r.sut_profile else '[fail]'} | "
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
        "| STICKS ID | Evidence Kind | Status | Successful | Failed | Total | Success Rate |",
        "|---|---|:---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        ev = r.latest_execution
        if ev:
            lines.append(
                f"| `{r.sticks_campaign_id}` | `{ev.evidence_kind}` | **{r.status}** | "
                f"{ev.successful} | {ev.failed} | {ev.total} | {ev.success_rate:.1%} |"
            )
        else:
            lines.append(f"| `{r.sticks_campaign_id}` | - | **{r.status}** | - | - | - | - |")

    typed_scopes = [
        row for row in rows
        if row.latest_execution and row.latest_execution.evidence_kind == "typed_outcome"
    ]
    if typed_scopes:
        lines += ["", "## Bounded Typed-Outcome Scope", ""]
        lines.append(
            "Typed outcomes establish only the observed effects and scope recorded in their immutable "
            "receipts. They remain `PARTIAL`: they do not provide per-stage admission, binding, or "
            "independent-observation coverage for a full campaign."
        )
        lines.append("")
        for row in typed_scopes:
            lines.append(f"- `{row.sticks_campaign_id}`: {row.latest_execution.scope}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the legacy STICKS campaign coverage matrix."
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=None,
        help="Explicit directory of campaign run summaries; defaults to release/evidence.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for coverage_matrix.json and COVERAGE_MATRIX.md.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_json = output_dir / "coverage_matrix.json"
    output_markdown = output_dir / "COVERAGE_MATRIX.md"
    rows = build_matrix(evidence_dir=args.evidence_dir)
    generated_at = datetime.now().isoformat(timespec="seconds")

    report = {
        "generated_at": generated_at,
        "evidence_directory": display_path((args.evidence_dir or EVIDENCE_DIR).resolve()),
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

    output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(rows, generated_at, output_markdown)
    print("Coverage matrix written to:")
    print(f"  {output_json}")
    print(f"  {output_markdown}")
    print()
    print(f"  Total : {report['total']}")
    print(f"  COMPLETE : {report['complete']}")
    print(f"  PARTIAL  : {report['partial']}")
    print(f"  MISSING  : {report['missing']}")


if __name__ == "__main__":
    main()
