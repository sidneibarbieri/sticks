#!/usr/bin/env python3
"""
Audit macro synchronization between STICKS outputs and manuscript values.tex files.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
PAPER1_VALUES = REPO_ROOT / "ACM CCS - Paper 1" / "results" / "values.tex"
PAPER1_MAIN = REPO_ROOT / "ACM CCS - Paper 1" / "main.tex"
PAPER2_VALUES = REPO_ROOT / "ACM CCS - Paper 2" / "results" / "values.tex"
PAPER2_MAIN = REPO_ROOT / "ACM CCS - Paper 2" / "main.tex"
MEASUREMENT_VALUES = (
    PROJECT_ROOT / "measurement" / "sut" / "scripts" / "results" / "todo_values_latex.tex"
)
STICKS_VALUES = PROJECT_ROOT / "results" / "values.tex"
OUTPUT_JSON = PROJECT_ROOT / "results" / "paper_macro_audit.json"
OUTPUT_MD = PROJECT_ROOT / "results" / "PAPER_MACRO_AUDIT.md"
PAPER1_GENERATOR_SOURCE = (
    REPO_ROOT
    / "sticks-docker"
    / "measurement"
    / "scripts"
    / "analyze_campaigns.py"
)


def extract_defined_macros(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"\\newcommand\{\\([A-Za-z][A-Za-z0-9]+)\}", text))


def extract_used_macros(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"\\([A-Za-z][A-Za-z0-9]+)", text))


def audit_paper(values_path: Path, main_path: Path) -> dict:
    defined = extract_defined_macros(values_path)
    used = extract_used_macros(main_path)
    used_defined = sorted(defined & used)
    defined_unused = sorted(defined - used)
    return {
        "values_path": str(values_path),
        "main_path": str(main_path),
        "defined_macro_count": len(defined),
        "used_defined_macro_count": len(used_defined),
        "used_defined_macros": used_defined,
        "defined_but_unused_count": len(defined_unused),
        "defined_but_unused_sample": defined_unused[:20],
    }


def build_report() -> dict:
    paper1 = audit_paper(PAPER1_VALUES, PAPER1_MAIN)
    paper2 = audit_paper(PAPER2_VALUES, PAPER2_MAIN)
    completed = subprocess.run(
        [
            "python3",
            str(PAPER1_GENERATOR_SOURCE),
            "--bundle",
            str(PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"),
            "--output-latex",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    paper1_generated = set(
        re.findall(r"\\newcommand\{\\([A-Za-z][A-Za-z0-9]+)\}", completed.stdout)
    )
    paper1_defined = extract_defined_macros(PAPER1_VALUES)
    paper1_used = extract_used_macros(PAPER1_MAIN)
    paper1_generator_backed = sorted(paper1_defined & paper1_generated)
    paper1_generator_backed_used = sorted(set(paper1_generator_backed) & paper1_used)
    paper1_manuscript_only_used = sorted((paper1_defined - paper1_generated) & paper1_used)
    measurement_defined = extract_defined_macros(MEASUREMENT_VALUES)
    paper2_defined = extract_defined_macros(PAPER2_VALUES)
    paper2_used = extract_used_macros(PAPER2_MAIN)
    sticks_defined = extract_defined_macros(STICKS_VALUES)
    paper2_measurement_backed = sorted(paper2_defined & measurement_defined)
    paper2_manuscript_only = sorted(paper2_defined - measurement_defined)
    paper2_measurement_backed_used = sorted(set(paper2_measurement_backed) & paper2_used)
    paper2_manuscript_only_used = sorted(set(paper2_manuscript_only) & paper2_used)

    return {
        "generated_at": datetime.now().isoformat(),
        "paper1": paper1,
        "paper1_provenance": {
            "sync_status": (
                "fully_generator_backed"
                if not paper1_manuscript_only_used
                else "partial_generator_backing"
            ),
            "generator_source_path": str(PAPER1_GENERATOR_SOURCE),
            "generator_macro_count": len(paper1_generated),
            "paper_macro_count": len(paper1_defined),
            "generator_backed_count": len(paper1_generator_backed),
            "generator_backed_macros": paper1_generator_backed,
            "generator_backed_used_in_manuscript_count": len(
                paper1_generator_backed_used
            ),
            "generator_backed_used_in_manuscript": paper1_generator_backed_used,
            "manuscript_only_used_count": len(paper1_manuscript_only_used),
            "manuscript_only_used_macros": paper1_manuscript_only_used,
        },
        "paper2": paper2,
        "paper2_vs_measurement": {
            "measurement_values_path": str(MEASUREMENT_VALUES),
            "paper_values_path": str(PAPER2_VALUES),
            "measurement_macro_count": len(measurement_defined),
            "paper_macro_count": len(paper2_defined),
            "paper_missing_from_measurement_count": len(
                paper2_defined - measurement_defined
            ),
            "paper_missing_from_measurement": sorted(
                paper2_defined - measurement_defined
            ),
            "measurement_missing_from_paper_count": len(
                measurement_defined - paper2_defined
            ),
            "measurement_missing_from_paper": sorted(
                measurement_defined - paper2_defined
            ),
        },
        "paper2_provenance": {
            "sync_status": (
                "blocked" if paper2_manuscript_only else "measurement_backed"
            ),
            "measurement_backed_count": len(paper2_measurement_backed),
            "measurement_backed_macros": paper2_measurement_backed,
            "measurement_backed_used_in_manuscript_count": len(
                paper2_measurement_backed_used
            ),
            "measurement_backed_used_in_manuscript": paper2_measurement_backed_used,
            "manuscript_only_count": len(paper2_manuscript_only),
            "manuscript_only_macros": paper2_manuscript_only,
            "manuscript_only_used_in_manuscript_count": len(
                paper2_manuscript_only_used
            ),
            "manuscript_only_used_in_manuscript": paper2_manuscript_only_used,
            "measurement_source_path": str(MEASUREMENT_VALUES),
            "manuscript_source_path": str(PAPER2_VALUES),
        },
        "sticks_values_vs_papers": {
            "sticks_values_path": str(STICKS_VALUES),
            "sticks_macro_count": len(sticks_defined),
            "overlap_with_paper1": len(sticks_defined & extract_defined_macros(PAPER1_VALUES)),
            "overlap_with_paper2": len(sticks_defined & paper2_defined),
        },
    }


def write_markdown(report: dict) -> None:
    paper1 = report["paper1"]
    paper1_provenance = report["paper1_provenance"]
    paper2 = report["paper2"]
    paper2_vs_measurement = report["paper2_vs_measurement"]
    paper2_provenance = report["paper2_provenance"]
    sticks_values = report["sticks_values_vs_papers"]

    lines = [
        "# Paper Macro Audit",
        "",
        f"- Generated at: `{report['generated_at']}`",
        "",
        "## Paper 1",
        "",
        f"- Defined macros in `values.tex`: `{paper1['defined_macro_count']}`",
        f"- Macros both defined and used in `main.tex`: `{paper1['used_defined_macro_count']}`",
        f"- Sample used macros: `{', '.join(paper1['used_defined_macros'][:20])}`",
        "",
        "## Paper 1 Macro Provenance",
        "",
        f"- Sync status: `{paper1_provenance['sync_status']}`",
        f"- Generator source: `{paper1_provenance['generator_source_path']}`",
        f"- Generator macro count: `{paper1_provenance['generator_macro_count']}`",
        f"- Generator-backed macros in Paper 1 values: `{paper1_provenance['generator_backed_count']}`",
        f"- Generator-backed macros used in manuscript: `{paper1_provenance['generator_backed_used_in_manuscript_count']}`",
        f"- Manuscript-used macros without generator backing: `{paper1_provenance['manuscript_only_used_count']}`",
        "",
        "## Paper 2",
        "",
        f"- Defined macros in `values.tex`: `{paper2['defined_macro_count']}`",
        f"- Macros both defined and used in `main.tex`: `{paper2['used_defined_macro_count']}`",
        "",
        "## Paper 2 vs Measurement Pipeline",
        "",
        f"- Measurement macro count: `{paper2_vs_measurement['measurement_macro_count']}`",
        f"- Paper 2 macro count: `{paper2_vs_measurement['paper_macro_count']}`",
        f"- Macros present in Paper 2 but absent from measurement output: `{paper2_vs_measurement['paper_missing_from_measurement_count']}`",
        f"- Macros present in measurement output but absent from Paper 2: `{paper2_vs_measurement['measurement_missing_from_paper_count']}`",
    ]

    if paper2_vs_measurement["paper_missing_from_measurement"]:
        lines.extend(
            [
                "",
                "### Paper 2 Macros Missing From Measurement Output",
                "",
            ]
        )
        lines.extend(
            f"- `{name}`"
            for name in paper2_vs_measurement["paper_missing_from_measurement"]
        )

    if paper2_vs_measurement["measurement_missing_from_paper"]:
        lines.extend(
            [
                "",
                "### Measurement Macros Missing From Paper 2",
                "",
            ]
        )
        lines.extend(
            f"- `{name}`"
            for name in paper2_vs_measurement["measurement_missing_from_paper"]
        )

    if paper1_provenance["manuscript_only_used_macros"]:
        lines.extend(
            [
                "",
                "### Paper 1 Manuscript-Used Macros Without Generator Backing",
                "",
            ]
        )
        lines.extend(
            f"- `{name}`" for name in paper1_provenance["manuscript_only_used_macros"]
        )

    lines.extend(
        [
            "",
            "## Paper 2 Macro Provenance",
            "",
            f"- Sync status: `{paper2_provenance['sync_status']}`",
            f"- Measurement-backed macros in Paper 2 values: `{paper2_provenance['measurement_backed_count']}`",
            f"- Measurement-backed macros used in manuscript: `{paper2_provenance['measurement_backed_used_in_manuscript_count']}`",
            f"- Manuscript-only macros in Paper 2 values: `{paper2_provenance['manuscript_only_count']}`",
            f"- Manuscript-only macros used in manuscript: `{paper2_provenance['manuscript_only_used_in_manuscript_count']}`",
            f"- Measurement source: `{paper2_provenance['measurement_source_path']}`",
            f"- Manuscript source: `{paper2_provenance['manuscript_source_path']}`",
        ]
    )

    if paper2_provenance["manuscript_only_macros"]:
        lines.extend(
            [
                "",
                "### Paper 2 Manuscript-Only Macros",
                "",
            ]
        )
        lines.extend(
            f"- `{name}`" for name in paper2_provenance["manuscript_only_macros"]
        )

    lines.extend(
        [
            "",
            "## Executable Subset Macros",
            "",
            "- `results/values.tex` tracks the executable published subset, not the Paper 2 measurement surface.",
            f"- Executable-subset macro count: `{sticks_values['sticks_macro_count']}`",
            f"- Overlap with Paper 1 values: `{sticks_values['overlap_with_paper1']}`",
            f"- Overlap with Paper 2 values: `{sticks_values['overlap_with_paper2']}`",
        ]
    )

    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_report()
    OUTPUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
