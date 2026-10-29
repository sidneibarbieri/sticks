#!/usr/bin/env python3
"""Audit a paper directory for build residue and for generated files it no longer uses.

Two kinds of clutter matter before a release. Build residue is what a LaTeX run leaves
behind; shipping it makes a reviewer's clone differ from the authors' tree for no reason.
A stale generated input is worse: a file under ``results/`` that the manuscript stopped
loading keeps its old numbers, and anyone reading the artifact cannot tell that LaTeX
ignores it.

The manuscript is the authority on which generated files are in scope, so this check reads
its ``\\input`` and figure/table macro arguments rather than carrying a hand-maintained allowlist that drifts.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAPER_DIR = PROJECT_ROOT.parent / "paper"

INPUT_PATTERN = re.compile(r"\\(?:input|researchfigure|researchtable)\{([^}]+)\}")
AUDITED_DIRECTORIES = ("results", "figures")
DOCUMENT_CLASS_PATTERN = re.compile(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}")
BIBLIOGRAPHY_STYLE_PATTERN = re.compile(r"\\bibliographystyle\{([^}]+)\}")
BACKUP_SUFFIX_MARKERS = ("-backup", ".bak", ".orig", ".save")

BUILD_RESIDUE_SUFFIXES = frozenset(
    {
        ".aux",
        ".bbl",
        ".blg",
        ".fdb_latexmk",
        ".fls",
        ".log",
        ".out",
        ".run.xml",
        ".synctex.gz",
        ".toc",
    }
)
IGNORED_NAMES = frozenset({".DS_Store"})


@dataclass(frozen=True)
class PaperHygieneReport:
    paper_dir: str
    build_residue: list[str]
    unreachable_sources: list[str]
    superseded_typesetting: list[str]

    @property
    def clean(self) -> bool:
        return not (
            self.build_residue or self.unreachable_sources or self.superseded_typesetting
        )


def _is_build_residue(path: Path) -> bool:
    return "".join(path.suffixes[-2:]) in BUILD_RESIDUE_SUFFIXES or (
        path.suffix in BUILD_RESIDUE_SUFFIXES
    )


def find_build_residue(paper_dir: Path) -> list[str]:
    return sorted(
        entry.name
        for entry in paper_dir.iterdir()
        if entry.is_file() and _is_build_residue(entry)
    )


def _declared_inputs(source: Path) -> set[str]:
    return set(INPUT_PATTERN.findall(source.read_text(encoding="utf-8")))


def reachable_inputs(paper_dir: Path) -> set[str]:
    """Every file the manuscript loads, following inputs through the files they load.

    A shared style file is reached by the figures that use it rather than by the manuscript
    directly, so a single pass over main.tex would wrongly report it as dead.
    """
    main_file = paper_dir / "main.tex"
    if not main_file.is_file():
        raise FileNotFoundError(f"no manuscript to audit against: {main_file}")

    reached: set[str] = set()
    pending = list(_declared_inputs(main_file))
    while pending:
        relative = pending.pop()
        if relative in reached:
            continue
        reached.add(relative)
        source = paper_dir / relative
        if source.is_file():
            pending.extend(_declared_inputs(source))
    return reached


def find_unreachable_sources(paper_dir: Path) -> list[str]:
    """Files under the audited directories that nothing in the manuscript loads."""
    reached = reachable_inputs(paper_dir)
    unreachable: list[str] = []
    for directory in AUDITED_DIRECTORIES:
        source_dir = paper_dir / directory
        if not source_dir.is_dir():
            continue
        for entry in sorted(source_dir.iterdir()):
            if not entry.is_file() or entry.name in IGNORED_NAMES:
                continue
            relative = f"{directory}/{entry.name}"
            if relative not in reached and f"{relative[:-4]}" not in reached:
                unreachable.append(relative)
    return unreachable


def find_superseded_typesetting(paper_dir: Path) -> list[str]:
    """Class and style files, and manuscript backups, the current manuscript does not name.

    Switching venue template leaves the previous class, its bibliography style, and a copy
    of the old manuscript behind. They still compile if someone reaches for them, which is
    exactly the risk.
    """
    main_text = (paper_dir / "main.tex").read_text(encoding="utf-8")
    kept = set()
    for match in DOCUMENT_CLASS_PATTERN.findall(main_text):
        kept.add(f"{match}.cls")
    for match in BIBLIOGRAPHY_STYLE_PATTERN.findall(main_text):
        kept.add(f"{match}.bst")

    superseded = []
    for entry in paper_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix in (".cls", ".bst") and entry.name not in kept:
            superseded.append(entry.name)
        elif any(entry.name.endswith(marker) for marker in BACKUP_SUFFIX_MARKERS):
            superseded.append(entry.name)
    return sorted(superseded)


def audit_paper(paper_dir: Path) -> PaperHygieneReport:
    return PaperHygieneReport(
        paper_dir=str(paper_dir),
        build_residue=find_build_residue(paper_dir),
        unreachable_sources=find_unreachable_sources(paper_dir),
        superseded_typesetting=find_superseded_typesetting(paper_dir),
    )


def print_human(report: PaperHygieneReport) -> None:
    status = "clean" if report.clean else "issues"
    print(f"[paper-hygiene] {report.paper_dir}: {status}")
    if report.build_residue:
        print(f"  build residue: {', '.join(report.build_residue)}")
    if report.unreachable_sources:
        print(f"  files the manuscript never loads: {', '.join(report.unreachable_sources)}")
    if report.superseded_typesetting:
        print(f"  superseded typesetting sources: {', '.join(report.superseded_typesetting)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-dir", type=Path, default=DEFAULT_PAPER_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = audit_paper(args.paper_dir.resolve())
    if args.json:
        print(json.dumps(asdict(report) | {"clean": report.clean}, indent=2))
    else:
        print_human(report)
    return 0 if report.clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
