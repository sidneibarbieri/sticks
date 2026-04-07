#!/usr/bin/env python3
"""Generate paper-ready traceability and LaTeX macros from release artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class ClaimEvidence:
    claim_id: str
    claim_text: str
    measured_value: str
    evidence_artifacts: List[str]


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required artifact not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_file(glob_pattern: str, base_dir: Path) -> Path | None:
    files = sorted(base_dir.glob(glob_pattern))
    return files[-1] if files else None


def _matrix_campaign_ids(matrix: dict) -> list[str]:
    return [row.get("campaign_id", "") for row in matrix.get("campaigns", [])]


def _scoped_fidelity_campaigns(matrix: dict, fidelity: dict) -> Dict[str, dict]:
    campaign_ids = {campaign_id for campaign_id in _matrix_campaign_ids(matrix) if campaign_id}
    fidelity_campaigns: Dict[str, dict] = fidelity.get("campaigns", {})
    return {
        campaign_id: payload
        for campaign_id, payload in fidelity_campaigns.items()
        if campaign_id in campaign_ids
    }


def _build_claims(
    matrix: dict,
    fidelity: dict,
    full_lab_report: Path | None,
    release_dir: Path,
) -> List[ClaimEvidence]:
    campaigns = matrix.get("campaigns", [])
    campaign_count = len(campaigns)

    pair_valid_count = sum(1 for row in campaigns if row.get("pair_valid") is True)
    success_no_fail_count = sum(
        1
        for row in campaigns
        if int(row.get("successful", 0)) == int(row.get("total_techniques", 0))
        and int(row.get("failed", 0)) == 0
    )

    fidelity_campaigns = _scoped_fidelity_campaigns(matrix, fidelity)
    rubric_total = sum(int(c.get("total", 0)) for c in fidelity_campaigns.values())
    rubric_consistent = sum(int(c.get("consistent", 0)) for c in fidelity_campaigns.values())
    rubric_mismatch = sum(int(c.get("mismatches", 0)) for c in fidelity_campaigns.values())

    full_lab_status = "N/A"
    full_lab_evidence = []
    if full_lab_report and full_lab_report.exists():
        lines = full_lab_report.read_text(encoding="utf-8").splitlines()[1:]
        total = 0
        passed = 0
        for line in lines:
            if not line.strip():
                continue
            total += 1
            cols = line.split("\t")
            if len(cols) >= 2 and cols[1] == "PASS":
                passed += 1
        full_lab_status = f"{passed}/{total} campaigns PASS"
        full_lab_evidence = [str(full_lab_report.relative_to(release_dir.parent))]

    claims = [
        ClaimEvidence(
            claim_id="CLAIM-PAIR-01",
            claim_text="Published campaign-SUT pair consistency validated by the loader.",
            measured_value=f"{pair_valid_count}/{campaign_count} pairs valid",
            evidence_artifacts=[
                "release/campaign_sut_fidelity_matrix.json",
                "src/loaders/campaign_loader.py",
            ],
        ),
        ClaimEvidence(
            claim_id="CLAIM-EXEC-01",
            claim_text="Latest execution snapshot shows successful completion without failed techniques.",
            measured_value=f"{success_no_fail_count}/{campaign_count} campaigns with failed=0",
            evidence_artifacts=["release/campaign_sut_fidelity_matrix.json"],
        ),
        ClaimEvidence(
            claim_id="CLAIM-RUBRIC-01",
            claim_text="Rubric computed fidelity remains consistent with declared fidelity.",
            measured_value=(
                f"consistent={rubric_consistent}/{rubric_total}, "
                f"mismatches={rubric_mismatch}"
            ),
            evidence_artifacts=[
                "release/fidelity_report.json",
                "release/fidelity_tables.tex",
                "sticks/data/abilities_registry/fidelity_rubric.py",
            ],
        ),
        ClaimEvidence(
            claim_id="CLAIM-FULLLAB-01",
            claim_text="Full-lab batch workflow status (canonical scripts).",
            measured_value=full_lab_status,
            evidence_artifacts=full_lab_evidence
            or [
                "release/evidence/health_<campaign>_<timestamp>.json",
                "release/evidence/<campaign>_<timestamp>/summary.json",
            ],
        ),
    ]

    return claims


def _write_traceability_md(path: Path, claims: List[ClaimEvidence]) -> None:
    lines = [
        "# Claim-to-Evidence Traceability",
        "",
        "Auto-generated from canonical release artifacts.",
        "",
        "| Claim ID | Claim | Measured Value | Evidence Artifacts |",
        "|---|---|---|---|",
    ]
    for claim in claims:
        artifacts = ", ".join(f"`{a}`" for a in claim.evidence_artifacts)
        lines.append(
            f"| {claim.claim_id} | {claim.claim_text} | {claim.measured_value} | {artifacts} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_traceability_json(path: Path, claims: List[ClaimEvidence]) -> None:
    payload = {
        "claims": [asdict(c) for c in claims],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_macros(path: Path, matrix: dict, fidelity: dict) -> None:
    campaigns = matrix.get("campaigns", [])
    campaign_count = len(campaigns)
    pair_valid_count = sum(1 for row in campaigns if row.get("pair_valid") is True)
    success_no_fail_count = sum(
        1
        for row in campaigns
        if int(row.get("successful", 0)) == int(row.get("total_techniques", 0))
        and int(row.get("failed", 0)) == 0
    )

    adapted_total = sum(int(row.get("adapted", 0)) for row in campaigns)
    inspired_total = sum(int(row.get("inspired", 0)) for row in campaigns)
    faithful_total = sum(int(row.get("faithful", 0)) for row in campaigns)
    total_techniques = sum(int(row.get("total_techniques", 0)) for row in campaigns)

    fidelity_campaigns = _scoped_fidelity_campaigns(matrix, fidelity)
    rubric_total = sum(int(c.get("total", 0)) for c in fidelity_campaigns.values())
    rubric_consistent = sum(int(c.get("consistent", 0)) for c in fidelity_campaigns.values())

    lines = [
        "% Auto-generated paper-ready macros",
        "% Scope: published campaigns with a matching SUT profile",
        "",
        f"\\newcommand{{\\formalCampaignCount}}{{{campaign_count}}}",
        f"\\newcommand{{\\pairValidCount}}{{{pair_valid_count}}}",
        f"\\newcommand{{\\executionNoFailCount}}{{{success_no_fail_count}}}",
        f"\\newcommand{{\\totalTechniquesAcrossCampaigns}}{{{total_techniques}}}",
        f"\\newcommand{{\\adaptedTechniqueCount}}{{{adapted_total}}}",
        f"\\newcommand{{\\inspiredTechniqueCount}}{{{inspired_total}}}",
        f"\\newcommand{{\\faithfulTechniqueCount}}{{{faithful_total}}}",
        f"\\newcommand{{\\rubricTechniqueTotal}}{{{rubric_total}}}",
        f"\\newcommand{{\\rubricConsistentTotal}}{{{rubric_consistent}}}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_full_lab_status_table(path: Path, matrix: dict) -> None:
    campaigns = matrix.get("campaigns", [])
    lines = [
        "% Auto-generated full-lab status table",
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Full-lab execution status by formal campaign-SUT pair}",
        r"\label{tab:full_lab_status}",
        r"\small",
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r"\textbf{Campaign} & \textbf{Total} & \textbf{Success} & \textbf{Failed} & \textbf{Adapted} & \textbf{Inspired} & \textbf{Pair Valid} \\",
        r"\midrule",
    ]
    for row in campaigns:
        pair_valid = "yes" if row.get("pair_valid") else "no"
        lines.append(
            f"{row.get('campaign_id','-')} & "
            f"{int(row.get('total_techniques', 0))} & "
            f"{int(row.get('successful', 0))} & "
            f"{int(row.get('failed', 0))} & "
            f"{int(row.get('adapted', 0))} & "
            f"{int(row.get('inspired', 0))} & "
            f"{pair_valid} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_claims_for_paper(path: Path, claims: List[ClaimEvidence]) -> None:
    lines = [
        "# Claims for Paper Text",
        "",
        "Use these measured statements directly in Results/Artifact sections.",
        "",
    ]
    for claim in claims:
        lines.append(f"## {claim.claim_id}")
        lines.append(f"- Claim: {claim.claim_text}")
        lines.append(f"- Measured value: {claim.measured_value}")
        lines.append("- Evidence:")
        for artifact in claim.evidence_artifacts:
            lines.append(f"  - `{artifact}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_summary(path: Path, claims: List[ClaimEvidence]) -> None:
    lines = [
        "# Paper-Ready Summary",
        "",
        "Scope:",
        "- `values.tex` and related macros summarize the published campaigns that currently have a matching SUT profile.",
        "- `results/CORPUS_STATE.md` remains the source for statements about the full published corpus.",
        "",
        "Generated files:",
        "- `release/campaign_sut_fidelity_matrix.json`",
        "- `release/CAMPAIGN_SUT_FIDELITY_MATRIX.md`",
        "- `release/fidelity_report.json`",
        "- `release/fidelity_tables.tex`",
        "- `release/claim_evidence_traceability.json`",
        "- `release/CLAIM_EVIDENCE_TRACEABILITY.md`",
        "- `release/paper_ready_macros.tex`",
        "- `release/values.tex`",
        "- `release/full_lab_status_table.tex`",
        "- `release/CLAIMS_FOR_PAPER.md`",
        "",
        "Top-level measured claims:",
    ]
    for claim in claims:
        lines.append(f"- `{claim.claim_id}`: {claim.measured_value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    root_dir = Path(__file__).resolve().parent.parent
    release_dir = root_dir / "release"
    results_dir = root_dir / "results"

    matrix = _load_json(release_dir / "campaign_sut_fidelity_matrix.json")
    fidelity = _load_json(release_dir / "fidelity_report.json")

    full_lab_report = _latest_file("full_lab_batch_*.tsv", release_dir)
    claims = _build_claims(matrix, fidelity, full_lab_report, release_dir)

    outputs = {
        "release": {
            "trace_json": release_dir / "claim_evidence_traceability.json",
            "trace_md": release_dir / "CLAIM_EVIDENCE_TRACEABILITY.md",
            "macros_tex": release_dir / "paper_ready_macros.tex",
            "values_tex": release_dir / "values.tex",
            "full_lab_table_tex": release_dir / "full_lab_status_table.tex",
            "claims_md": release_dir / "CLAIMS_FOR_PAPER.md",
            "summary_md": release_dir / "PAPER_READY_SUMMARY.md",
        },
        "results": {
            "trace_json": results_dir / "claim_evidence_traceability.json",
            "trace_md": results_dir / "CLAIM_EVIDENCE_TRACEABILITY.md",
            "macros_tex": results_dir / "paper_ready_macros.tex",
            "values_tex": results_dir / "values.tex",
            "full_lab_table_tex": results_dir / "full_lab_status_table.tex",
            "claims_md": results_dir / "CLAIMS_FOR_PAPER.md",
            "summary_md": results_dir / "PAPER_READY_SUMMARY.md",
        },
    }

    for scope, scope_outputs in outputs.items():
        _write_traceability_json(scope_outputs["trace_json"], claims)
        _write_traceability_md(scope_outputs["trace_md"], claims)
        _write_macros(scope_outputs["macros_tex"], matrix, fidelity)
        _write_macros(scope_outputs["values_tex"], matrix, fidelity)
        _write_full_lab_status_table(scope_outputs["full_lab_table_tex"], matrix)
        _write_claims_for_paper(scope_outputs["claims_md"], claims)
        _write_summary(scope_outputs["summary_md"], claims)

        print(f"[OK] {scope_outputs['trace_json']}")
        print(f"[OK] {scope_outputs['trace_md']}")
        print(f"[OK] {scope_outputs['macros_tex']}")
        print(f"[OK] {scope_outputs['values_tex']}")
        print(f"[OK] {scope_outputs['full_lab_table_tex']}")
        print(f"[OK] {scope_outputs['claims_md']}")
        print(f"[OK] {scope_outputs['summary_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
