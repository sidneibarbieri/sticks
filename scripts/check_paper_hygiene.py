#!/usr/bin/env python3
"""
Audit paper directories for unnecessary residue and avoidable clutter.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", SCRIPT_ROOT))
PAPER_DIRS = {
    "paper1": WORKSPACE_ROOT / "ACM CCS - Paper 1",
    "paper2": WORKSPACE_ROOT / "ACM CCS - Paper 2",
}
ROOT_RESIDUE_NAMES = {
    "main.aux",
    "main.bbl",
    "main.blg",
    "main.fdb_latexmk",
    "main.fls",
    "main.log",
    "main.out",
    "main.run.xml",
    "main.synctex.gz",
}
ALLOWED_RESULTS_NAMES = {"values.tex"}


@dataclass
class PaperHygieneReport:
    paper: str
    root_residue: list[str]
    results_extras: list[str]

    @property
    def clean(self) -> bool:
        return not self.root_residue and not self.results_extras


def check_root_residue(paper_dir: Path) -> list[str]:
    return sorted(name for name in ROOT_RESIDUE_NAMES if (paper_dir / name).exists())


def check_results_directory(paper_dir: Path) -> list[str]:
    results_dir = paper_dir / "results"
    if not results_dir.exists():
        return ["results/ (missing)"]

    extras: list[str] = []
    for entry in sorted(results_dir.iterdir()):
        if entry.name == ".DS_Store":
            continue
        if entry.name not in ALLOWED_RESULTS_NAMES:
            extras.append(f"results/{entry.name}")
    return extras


def audit_paper(paper: str, paper_dir: Path) -> PaperHygieneReport:
    return PaperHygieneReport(
        paper=paper,
        root_residue=check_root_residue(paper_dir),
        results_extras=check_results_directory(paper_dir),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", choices=["paper1", "paper2", "all"], default="all")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def selected_papers(name: str) -> dict[str, Path]:
    if name == "all":
        return PAPER_DIRS
    return {name: PAPER_DIRS[name]}


def print_human(reports: list[PaperHygieneReport]) -> None:
    for report in reports:
        status = "clean" if report.clean else "issues"
        print(f"[paper-hygiene] {report.paper}: {status}")
        if report.root_residue:
            print(f"  root residue: {', '.join(report.root_residue)}")
        if report.results_extras:
            print(f"  results extras: {', '.join(report.results_extras)}")


def main() -> int:
    args = parse_args()
    reports = [
        audit_paper(paper, paper_dir)
        for paper, paper_dir in selected_papers(args.paper).items()
    ]

    if args.json:
        print(json.dumps([asdict(report) | {"clean": report.clean} for report in reports], indent=2))
    else:
        print_human(reports)

    return 0 if all(report.clean for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
