#!/usr/bin/env python3
"""
Create a paper-scoped review artifact for ACM CCS Paper 2.

The staged artifact preserves the directory layout expected by release_check.sh
while excluding unrelated project material, especially Paper 1 and optional
runtime exploration assets not needed to reproduce the measurement claims.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SUT_ROOT = SCRIPT_DIR.parent
STICKS_ROOT = SUT_ROOT.parent.parent
REPO_ROOT = STICKS_ROOT.parent
PAPER2_ROOT = REPO_ROOT / "ACM CCS - Paper 2"
DEFAULT_DEST = REPO_ROOT / "artifacts" / "paper2-review-artifact"
PUBLISHED_REPOSITORY = "https://github.com/sidneibarbieri/sticks"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dest: Path) -> None:
    ensure_parent(dest)
    shutil.copy2(src, dest)


def copy_optional_file(src: Path, dest: Path) -> None:
    if src.exists():
        copy_file(src, dest)


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


def stage_paper(dest_root: Path) -> None:
    paper_dest = dest_root / "ACM CCS - Paper 2"
    keep_files = [
        "main.tex",
        "main.pdf",
        "references.bib",
        "references_official_downloaded.bib",
        "used_citations_only.bib",
        "acmart.cls",
        "ACM-Reference-Format.bst",
        "results/values.tex",
    ]
    for relative in keep_files:
        copy_optional_file(PAPER2_ROOT / relative, paper_dest / relative)

    copy_tree(PAPER2_ROOT / "figures", paper_dest / "figures")


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
    for relative in ["build_manuscript.py", "check_paper_hygiene.py"]:
        copy_file(
            STICKS_ROOT / "scripts" / relative,
            dest_root / "sticks" / "scripts" / relative,
        )

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
                "ACM CCS - Paper 2/build_artifacts/",
                "ACM CCS - Paper 2/*.aux",
                "ACM CCS - Paper 2/*.bbl",
                "ACM CCS - Paper 2/*.blg",
                "ACM CCS - Paper 2/*.fdb_latexmk",
                "ACM CCS - Paper 2/*.fls",
                "ACM CCS - Paper 2/*.log",
                "ACM CCS - Paper 2/*.out",
                "ACM CCS - Paper 2/*.run.xml",
                "ACM CCS - Paper 2/*.synctex.gz",
                "",
            ]
        ),
    )

    write_text(
        dest_root / "README.md",
        "\n".join(
            [
                "# Paper 2 Review Artifact",
                "",
                "This staging directory contains the minimal reproducibility surface for",
                "the Paper 2 measurement manuscript on environment semantics in structured CTI.",
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
                "This wrapper is the reviewer-facing entry point used by the paper.",
                "It jumps to the canonical verifier",
                "(`sticks/measurement/sut/release_check.sh`) and reruns the full",
                "measurement-to-manuscript validation path.",
                "",
                "This public review artifact intentionally focuses on the measurement and",
                "validation path cited by the paper. Heavier lab-orchestration helpers",
                "from the full development workspace are not required for reproducing",
                "the reported measurement claims and are therefore not part of this",
                "staged repository.",
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
                "- `ACM CCS - Paper 2/`: manuscript source plus the current built PDF.",
                "- `sticks/measurement/sut/`: measurement code, verifier, docs, and audit-facing data.",
                "- `sticks/scripts/`: manuscript sync/build helpers used by the verifier.",
                "- `sticks/measurement/sut/scripts/results/`: generated audit outputs refreshed by the verifier.",
                "- `sticks/results/`: generated manuscript-sync reports refreshed by the verifier.",
                "",
                "## What is intentionally included",
                "",
                "- The Paper 2 manuscript sources needed to rebuild the PDF.",
                "- The current built manuscript PDF for read-before-run inspection.",
                "- The measurement pipeline and figure/traceability generators.",
                "- The five bundle snapshots used by the paper.",
                "- The manuscript-value synchronizer used by `release_check.sh`.",
                "",
                "## What is intentionally excluded",
                "",
                "- Paper 1 sources and results.",
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
                "- `ACM CCS - Paper 2/`: manuscript source, bibliography, class/bst files, rendered figure templates, and `results/values.tex`.",
                "- `sticks/measurement/sut/release_check.sh`: canonical verifier called by the paper-cited wrapper.",
                "- `sticks/measurement/sut/scripts/`: only the scripts required by the verifier.",
                "- `sticks/measurement/sut/scripts/data/`: the five STIX/ATT&CK-related bundle snapshots used in the measurements.",
                "- `sticks/scripts/sync_manuscript_values.py`: Paper-2-only macro synchronization helper.",
                "",
                "## Excluded components",
                "",
                "- Paper 1 manuscript sources and analysis pipeline.",
                "- Optional runtime and cyber-range execution tooling.",
                "- Large historical result archives and host-specific temporary outputs.",
                "",
                "## Reproduction contract",
                "",
                "If `bash run_review_check.sh` passes from the repository root, the staged artifact has",
                "enough material to rerun the measurement pipeline, regenerate tables/figures,",
                "synchronize manuscript values, and rebuild the Paper 2 PDF.",
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

    stage_paper(dest_root)
    stage_measurement_artifact(dest_root)
    write_artifact_docs(dest_root)

    print(f"Staged Paper 2 artifact at {dest_root}")


if __name__ == "__main__":
    main()
