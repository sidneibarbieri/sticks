#!/usr/bin/env python3
"""
Create a venue-neutral reproducibility artifact for the environment study.

The staged artifact preserves the directory layout expected by release_check.sh
while excluding unrelated project material and optional runtime exploration
assets not needed to reproduce the released measurement claims.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SUT_ROOT = SCRIPT_DIR.parent
STICKS_ROOT = SUT_ROOT.parent.parent
REPO_ROOT = STICKS_ROOT.parent
DEFAULT_DEST = REPO_ROOT / "artifacts" / "paper2-review-artifact"
PUBLISHED_REPOSITORY = "https://github.com/sidneibarbieri/sticks"
PAPER_TITLE = "The Environment Semantics Gap in Structured CTI: Measuring SUT Requirements for APT Emulation"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dest: Path) -> None:
    ensure_parent(dest)
    shutil.copy2(src, dest)


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            ".pytest_cache",
            "*.pyc",
            ".DS_Store",
        ),
    )


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def stage_measurement_artifact(dest_root: Path) -> None:
    keep_root_files = [
        "release_check.sh",
        "README.md",
        "README_REPRODUCIBILITY.md",
        "CLAIMS_TO_EVIDENCE.md",
        "FINAL_REVIEW_READINESS.md",
        "PUBLICATION_CHECKLIST.md",
        "requirements.txt",
    ]
    for relative in keep_root_files:
        copy_file(SUT_ROOT / relative, dest_root / "sticks" / "measurement" / "sut" / relative)

    keep_scripts = [
        "sut_measurement_pipeline.py",
        "render_figures.py",
        "generate_traceability.py",
        "evaluate_compatibility_validation.py",
        "sanitize_bibliography_policy.py",
        "package_paper2_artifact.py",
    ]
    for relative in keep_scripts:
        copy_file(
            SCRIPT_DIR / relative,
            dest_root / "sticks" / "measurement" / "sut" / "scripts" / relative,
        )

    copy_tree(SCRIPT_DIR / "data", dest_root / "sticks" / "measurement" / "sut" / "scripts" / "data")
    copy_file(
        STICKS_ROOT / "scripts" / "sync_manuscript_values.py",
        dest_root / "sticks" / "scripts" / "sync_manuscript_values.py",
    )
    copy_file(STICKS_ROOT / "LICENSE", dest_root / "LICENSE")

    for directory in [
        dest_root / "sticks" / "measurement" / "sut" / "scripts" / "results",
        dest_root / "sticks" / "results",
        dest_root / "tmp",
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def write_artifact_docs(dest_root: Path) -> None:
    write_text(
        dest_root / "run_review_check.sh",
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'ROOT_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"',
                'cd \"$ROOT_DIR/sticks/measurement/sut\"',
                "bash release_check.sh",
                "",
            ]
        ),
    )
    (dest_root / "run_review_check.sh").chmod(0o755)

    write_text(
        dest_root / ".gitattributes",
        "\n".join(
            [
                "* text=auto eol=lf",
                "*.sh text eol=lf",
                "*.py text eol=lf",
                "*.tex text eol=lf",
                "",
            ]
        ),
    )

    write_text(
        dest_root / ".gitignore",
        "\n".join(
            [
                ".DS_Store",
                "__pycache__/",
                "*.pyc",
                "tmp/",
                "",
            ]
        ),
    )

    write_text(
        dest_root / "README.md",
        "\n".join(
            [
                "# Environment Reproducibility Artifact",
                "",
                "This staging directory contains the minimal reproducibility surface for",
                "the environment-semantics measurement study in structured CTI.",
                "",
                f"Paper title: {PAPER_TITLE}.",
                "",
                "Suggested public repository name: `sticks`.",
                "",
                "## Public clone path",
                "",
                "```bash",
                f"git clone {PUBLISHED_REPOSITORY}.git",
                "cd sticks",
                "bash run_review_check.sh",
                "```",
                "",
                "```bash",
                "bash run_review_check.sh",
                "```",
                "",
                "This wrapper is the reviewer-facing entry point.",
                "It jumps to the canonical verifier",
                "(`sticks/measurement/sut/release_check.sh`) and reruns the full",
                "measurement validation path.",
                "",
                "This public review artifact intentionally focuses on the measurement and",
                "validation path cited by the paper. Heavier lab-orchestration helpers",
                "from the full development workspace are not required for reproducing",
                "the reported measurement claims and are therefore not part of this",
                "staged repository.",
                "",
                "## What the reviewer can verify directly",
                "",
                "- Retrieval: the repository is public, self-contained, and includes a `LICENSE`.",
                "- Exercisability: `bash run_review_check.sh` drives the full reviewer path end to end.",
                "- Main-result reproduction: the command refreshes the released measurement outputs",
                "  and verifies that the generated values remain consistent with the released reports.",
                "",
                "## Runtime expectations",
                "",
                "- Python 3.11+",
                "- A TeX environment with `latexmk`/`pdflatex` available",
                "- Poppler tools (`pdftoppm`, `pdfinfo`) available on `PATH`",
                "- Rough runtime on a laptop-class machine: about 40 seconds for the full check",
                "- No network access, API keys, Caldera, or container runtime required once cloned",
                "",
                "## Repository layout",
                "",
                "- `run_review_check.sh`: root-level wrapper for the reviewer path.",
                "- `sticks/measurement/sut/`: measurement code, verifier, docs, and audit-facing data.",
                "- `sticks/scripts/`: shared helper scripts used by the verifier.",
                "- `sticks/measurement/sut/scripts/results/`: generated audit outputs refreshed by the verifier.",
                "- `sticks/results/`: generated manuscript-sync reports refreshed by the verifier.",
                "",
                "## What is intentionally included",
                "",
                "- The measurement pipeline and figure/traceability generators.",
                "- The five bundle snapshots used by the paper.",
                "- The output synchronizer used by `release_check.sh` when a private manuscript tree is present.",
                "",
                "## What is intentionally excluded",
                "",
                "- Private manuscript trees and submission-specific files.",
                "- Optional Caldera or runtime orchestration material not required for the measurement claims.",
                "- Workspace-local temporary files, historical logs, and exploratory side outputs.",
                "",
                "The goal is auditability with minimal reviewer friction.",
                "",
            ]
        ),
    )

    write_text(
        dest_root / "ARTIFACT_MANIFEST.md",
        "\n".join(
            [
                "# Artifact Manifest",
                "",
                "Suggested repository name: `sticks`.",
                "",
                f"Public repository URL: `{PUBLISHED_REPOSITORY}`.",
                "",
                "## Included components",
                "",
                "- `run_review_check.sh`: root-level reviewer entrypoint.",
                "- `sticks/measurement/sut/release_check.sh`: canonical verifier called by the paper-cited wrapper.",
                "- `sticks/measurement/sut/scripts/`: only the scripts required by the verifier.",
                "- `sticks/measurement/sut/scripts/data/`: the five STIX/ATT&CK-related bundle snapshots used in the measurements.",
                "- `sticks/scripts/sync_manuscript_values.py`: optional manuscript synchronization helper for private workspace use.",
                "",
                "## Excluded components",
                "",
                "- Private manuscript sources and submission-specific assets.",
                "- Optional runtime and cyber-range execution tooling.",
                "- Large historical result archives and host-specific temporary outputs.",
                "",
                "## Reproduction contract",
                "",
                "If `bash run_review_check.sh` passes from the repository root, the staged artifact has",
                "enough material to rerun the measurement pipeline, regenerate tables/figures,",
                "and refresh the released audit outputs.",
                "",
                "The intended publication surface for this repository is the tagged public revision",
                "of the artifact itself. If a DOI-backed archival snapshot is later created, it should",
                "point to the same tagged contents.",
                "",
            ]
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help="Destination directory for the staged review artifact.",
    )
    args = parser.parse_args()

    dest_root = args.dest.resolve()
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    stage_measurement_artifact(dest_root)
    write_artifact_docs(dest_root)

    print(f"Staged environment artifact at {dest_root}")


if __name__ == "__main__":
    main()
