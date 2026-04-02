#!/usr/bin/env python3
"""
Build a manuscript while keeping root-level LaTeX residue out of the paper dir.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from pathlib import Path
from typing import Iterable


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
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


def resolve_paper_dir(paper: str | None, paper_dir: str | None) -> Path:
    if paper_dir:
        return Path(paper_dir).resolve()
    if paper:
        return PAPER_DIRS[paper]
    raise ValueError("Either --paper or --paper-dir must be provided.")


def clean_root_residue(paper_dir: Path) -> None:
    for file_name in ROOT_RESIDUE_NAMES:
        file_path = paper_dir / file_name
        if file_path.exists():
            file_path.unlink()


def settle_root_residue(paper_dir: Path, attempts: int = 10, delay_seconds: float = 0.3) -> None:
    for _ in range(attempts):
        clean_root_residue(paper_dir)
        time.sleep(delay_seconds)
    clean_root_residue(paper_dir)


def ensure_build_dir(paper_dir: Path) -> Path:
    build_dir = paper_dir / "build_artifacts"
    build_dir.mkdir(exist_ok=True)
    return build_dir


def build_command(build_dir: Path) -> list[str]:
    return [
        "latexmk",
        "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-auxdir=build_artifacts",
        "-emulate-aux-dir",
        f"-outdir={build_dir.name}",
        "main.tex",
    ]


def run_build(paper_dir: Path, build_dir: Path) -> None:
    subprocess.run(
        build_command(build_dir),
        cwd=paper_dir,
        check=True,
    )


def copy_pdf_to_root(paper_dir: Path, build_dir: Path) -> None:
    pdf_path = build_dir / "main.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(f"Expected PDF not found: {pdf_path}")
    shutil.copy2(pdf_path, paper_dir / "main.pdf")


def build_manuscript(paper_dir: Path) -> None:
    settle_root_residue(paper_dir)
    build_dir = ensure_build_dir(paper_dir)
    run_build(paper_dir, build_dir)
    copy_pdf_to_root(paper_dir, build_dir)
    settle_root_residue(paper_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", choices=sorted(PAPER_DIRS))
    parser.add_argument("--paper-dir")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paper_dir = resolve_paper_dir(args.paper, args.paper_dir)
    build_manuscript(paper_dir)
    print(f"[build-manuscript] Built {paper_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
