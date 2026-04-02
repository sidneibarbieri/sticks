#!/usr/bin/env python3
"""
Synchronize manuscript values.tex files from the current STICKS measurement outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
PAPER2_MEASUREMENT_VALUES = (
    PROJECT_ROOT / "measurement" / "sut" / "scripts" / "results" / "todo_values_latex.tex"
)
PAPER1_ANALYSIS_CMD = [
    "python3",
    str(PROJECT_ROOT / "scripts" / "analyze_campaigns.py"),
    "--bundle",
    str(PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"),
    "--output-latex",
]
OUTPUT_JSON = PROJECT_ROOT / "results" / "manuscript_values_sync.json"
OUTPUT_MD = PROJECT_ROOT / "results" / "MANUSCRIPT_VALUES_SYNC.md"


def resolve_paper_dir(env_var: str, paper_name: str) -> Path:
    env_value = os.environ.get(env_var)
    if env_value:
        candidate = Path(env_value)
        if candidate.exists():
            return candidate
    for candidate in (REPO_ROOT / paper_name, PROJECT_ROOT / paper_name):
        if candidate.exists():
            return candidate
    return REPO_ROOT / paper_name


PAPER1_DIR = resolve_paper_dir("PAPER1_DIR", "ACM CCS - Paper 1")
PAPER2_DIR = resolve_paper_dir("PAPER_DIR", "ACM CCS - Paper 2")
PAPER1_VALUES = PAPER1_DIR / "results" / "values.tex"
PAPER2_VALUES = PAPER2_DIR / "results" / "values.tex"


@dataclass
class SyncResult:
    paper: str
    status: str
    details: str
    macros_written: int = 0


def extract_macros(text: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in re.finditer(
            r"\\newcommand\{\\([A-Za-z][A-Za-z0-9]+)\}\{([^}]*)\}",
            text,
        )
    }


def extract_used_macros(text: str) -> set[str]:
    return set(re.findall(r"\\([A-Za-z][A-Za-z0-9]+)", text))


def sync_paper1(dry_run: bool, write_output: bool) -> SyncResult:
    completed = subprocess.run(
        PAPER1_ANALYSIS_CMD,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    generated_values_text = completed.stdout
    generated_macros = extract_macros(generated_values_text)
    paper_main_text = (PAPER1_DIR / "main.tex").read_text(encoding="utf-8")
    current_defined_macros = set(extract_macros(PAPER1_VALUES.read_text(encoding="utf-8")))
    missing_manuscript_macros = sorted(
        (extract_used_macros(paper_main_text) & current_defined_macros) - set(generated_macros)
    )
    if missing_manuscript_macros:
        return SyncResult(
            paper="paper1",
            status="blocked",
        details=(
                "Paper 1 still uses macros that are absent from "
                "scripts/analyze_campaigns.py output: "
                + ", ".join(missing_manuscript_macros)
            ),
            macros_written=0,
        )

    current_text = PAPER1_VALUES.read_text(encoding="utf-8")
    if write_output and not dry_run:
        PAPER1_VALUES.write_text(generated_values_text, encoding="utf-8")
        status = "updated" if current_text != generated_values_text else "current"
        details = (
            "Paper 1 values.tex replaced from the canonical analyze_campaigns.py output."
            if current_text != generated_values_text
            else "Paper 1 values.tex already matched the canonical analyze_campaigns.py output."
        )
    elif dry_run and write_output:
        status = "dry_run"
        details = "Paper 1 sync checked against the canonical analyze_campaigns.py output."
    else:
        status = "checked"
        details = "Paper 1 current values.tex checked against the canonical analyze_campaigns.py output."

    return SyncResult(
        paper="paper1",
        status=status,
        details=details,
        macros_written=len(generated_macros),
    )


def sync_paper2(dry_run: bool, write_output: bool) -> SyncResult:
    measurement_text = PAPER2_MEASUREMENT_VALUES.read_text(encoding="utf-8")
    paper_text = PAPER2_VALUES.read_text(encoding="utf-8")
    main_text = (PAPER2_DIR / "main.tex").read_text(encoding="utf-8")

    measurement_macros = extract_macros(measurement_text)
    paper_macros = extract_macros(paper_text)
    manuscript_macros = sorted(set(paper_macros) & extract_used_macros(main_text))
    missing_from_measurement = sorted(set(manuscript_macros) - set(measurement_macros))
    if missing_from_measurement:
        return SyncResult(
            paper="paper2",
            status="blocked",
            details=(
                "Paper 2 contains macros without canonical source in "
                "measurement/sut/scripts/results/todo_values_latex.tex "
                "that are still used in main.tex: "
                + ", ".join(missing_from_measurement)
            ),
            macros_written=0,
        )

    if write_output and not dry_run:
        PAPER2_VALUES.write_text(measurement_text, encoding="utf-8")
        status = "updated" if paper_text != measurement_text else "current"
        details = (
            "Paper 2 values.tex replaced from measurement pipeline output."
            if paper_text != measurement_text
            else "Paper 2 values.tex already matched measurement pipeline output."
        )
    elif dry_run and write_output:
        status = "dry_run"
        details = "Paper 2 sync checked against measurement pipeline output."
    else:
        status = "checked"
        details = "Paper 2 current values.tex checked against measurement pipeline output."

    return SyncResult(
        paper="paper2",
        status=status,
        details=details,
        macros_written=len(measurement_macros),
    )


def write_report(results: list[SyncResult]) -> None:
    payload = {
        "generated_at": datetime.now().isoformat(),
        "results": [result.__dict__ for result in results],
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Manuscript Values Sync",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        "",
    ]
    for result in results:
        lines.extend(
            [
                f"## {result.paper}",
                "",
                f"- Status: `{result.status}`",
                f"- Macros written: `{result.macros_written}`",
                f"- Details: {result.details}",
                "",
            ]
        )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--paper",
        choices=["paper1", "paper2", "all"],
        default="all",
        help="Restrict synchronization to one manuscript.",
    )
    args = parser.parse_args()

    results: list[SyncResult] = []
    if args.paper in {"paper1", "all"}:
        results.append(sync_paper1(dry_run=args.dry_run, write_output=True))
    if args.paper in {"paper2", "all"}:
        results.append(sync_paper2(dry_run=args.dry_run, write_output=True))

    write_report(results)

    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")
    if any(result.status == "blocked" for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
