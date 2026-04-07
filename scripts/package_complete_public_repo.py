#!/usr/bin/env python3
"""
Stage a complete but sanitized public repository for the STICKS artifact.

This package is intentionally broader than the minimal review artifact: it
retains the canonical smoke path, the VM-backed lab helpers, and the current
evidence/results needed to reproduce the study outputs and inspect the heavier
realism path. Runtime VM images, local caches, and developer-only
secrets/configs are excluded.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STICKS_ROOT = REPO_ROOT / "sticks"
DEFAULT_DEST = REPO_ROOT / "artifacts" / "paper2-public-complete"
PUBLISHED_REPOSITORY = "https://github.com/sidneibarbieri/sticks"

ROOT_FILES = [
    ".gitignore",
    ".python-version",
    "ARCHITECTURE.md",
    "LICENSE",
    "MANIFEST.md",
    "PUBLIC_REPOSITORY_SCOPE.md",
    "README.md",
    "README_MULTI_VM.md",
    "REPRODUCIBILITY.md",
    "REVIEWER_GUIDE.md",
    "Vagrantfile",
    "apply_sut_profile.py",
    "multi_vm_manager.py",
    "pyproject.toml",
    "pyrightconfig.json",
    "requirements.txt",
    "run_review_check.sh",
    "run_vm_backed_campaign.sh",
    "setup.sh",
    "vagrant-multi.sh",
    "vagrant-wrapper.sh",
]

ROOT_DIRS = [
    "artifact",
    "campaigns",
    "data",
    "docs",
    "infra",
    "lab",
    "measurement",
    "release",
    "results",
    "scripts",
    "src",
    "tests",
]

def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dest: Path) -> None:
    ensure_parent(dest)
    shutil.copy2(src, dest)


def ignore_for_directory(directory: str):
    directory_path = STICKS_ROOT / directory

    def _ignore(src: str, names: list[str]) -> set[str]:
        src_path = Path(src)
        ignored: set[str] = set()

        common = {
            ".DS_Store",
            ".pytest_cache",
            "__pycache__",
        }
        ignored.update(name for name in names if name in common)
        ignored.update(name for name in names if name.endswith(".pyc"))

        rel = src_path.relative_to(directory_path)

        # Exclude local VM state and generated qemu assets from the public repo.
        if rel == Path("vagrant"):
            ignored.add(".vagrant")
        if rel == Path("qemu"):
            if "runtime" in names:
                ignored.add("runtime")
        if rel == Path("qemu/images"):
            ignored.update(name for name in names if name.endswith(".img"))
        if rel == Path("provisioning/cloud-init"):
            ignored.update(
                {
                    "meta-data",
                    "seed.iso",
                    "user-data",
                    "vars.fd",
                    "run-overlay.qcow2",
                    "iso-root",
                }
            )

        # Exclude developer-local Caldera config from publication.
        if rel == Path("sut/caldera_conf"):
            ignored.add("local.yml")

        if rel == Path("sut"):
            ignored.add("SCRIPT_ANALYSIS.md")
        if rel == Path("sut/scripts"):
            ignored.add("llm_environment_inference.py")
        if rel == Path("sut/scripts/results/audit"):
            ignored.add("llm")

        # Exclude obviously local or superseded runtime residue.
        if rel == Path():
            ignored.update(
                {
                    "service_payload.log",
                }
            )
            if directory == "measurement":
                ignored.update(
                    {
                        ".env",
                        "meta",
                        "PUBLISHING_CHECKLIST.md",
                        "GIT_READY_MANIFEST.md",
                        "MEASUREMENT_DOD.md",
                    }
                )
            if directory == "docs":
                ignored.update(
                    {
                        "legacy_preserved",
                        "validation_report.md",
                        "WINDOWS_FIDELITY_CLASSIFICATION.md",
                        "LEGACY_CLEANUP_CANDIDATES.md",
                        "CANONICAL_STRUCTURE.md",
                    }
                )
            if directory == "scripts":
                ignored.update(
                    {
                        "build_manuscript.py",
                        "check_paper_hygiene.py",
                        "generate_separated_corpus.py",
                        "submission_freeze.sh",
                        "audit_paper_macros.py",
                    }
                )
            if directory == "results":
                for name in names:
                    if (
                        name in {"evidence", "frozen", "VALIDATION_REPORT.md", "validation_report_latest.json"}
                        or name.startswith("validation_report_")
                        or name.startswith("submission_freeze_")
                        or name.startswith("full_lab_batch_")
                        or name.startswith("paper1_")
                        or name.startswith("PAPER1_")
                        or name in {
                            "PUBLIC_SURFACE_REPORT.md",
                            "PAPER_MACRO_AUDIT.md",
                            "paper_macro_audit.json",
                            "PAPER_MEASUREMENTS.md",
                            "paper_measurements.json",
                            "campaign_results_consolidated.json",
                            "public_surface_report.json",
                        }
                    ):
                        ignored.add(name)
            if directory == "release":
                for name in names:
                    if (
                        name == "evidence"
                        or name.startswith("submission_freeze_")
                        or name.startswith("full_lab_batch_")
                    ):
                        ignored.add(name)

        return ignored

    return _ignore


def copy_tree(src: Path, dest: Path, directory_name: str | None = None) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    ignore = (
        ignore_for_directory(directory_name)
        if directory_name is not None
        else shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".DS_Store")
    )
    shutil.copytree(src, dest, ignore=ignore)


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def stage_root(dest_root: Path) -> None:
    for relative in ROOT_FILES:
        src = STICKS_ROOT / relative
        if src.exists():
            copy_file(src, dest_root / relative)

    for relative in ROOT_DIRS:
        src = STICKS_ROOT / relative
        if src.exists():
            copy_tree(src, dest_root / relative, relative)


def write_repo_docs(dest_root: Path) -> None:
    write_text(
        dest_root / "run_review_check.sh",
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'ROOT_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"',
                'cd \"$ROOT_DIR/measurement/sut\"',
                "bash release_check.sh",
                "",
            ]
        ),
    )
    (dest_root / "run_review_check.sh").chmod(0o755)

    write_text(
        dest_root / "run_vm_backed_campaign.sh",
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'ROOT_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"',
                'cd \"$ROOT_DIR\"',
                'campaign=\"${1:-0.c0011}\"',
                "python3 scripts/run_lab_campaign.py --campaign \"$campaign\"",
                "",
            ]
        ),
    )
    (dest_root / "run_vm_backed_campaign.sh").chmod(0o755)

    write_text(
        dest_root / "ARTIFACT_MANIFEST.md",
        "\n".join(
            [
                "# Complete Public Artifact Manifest",
                "",
                f"Public repository URL: `{PUBLISHED_REPOSITORY}`.",
                "",
                "## Included",
                "",
                "- Full STICKS code needed for the canonical smoke path.",
                "- VM-backed lab helpers and SUT-application code used for realism checks.",
                "- Current synthesized release/results reports used to ground paper claims.",
                "- Current synthesized outputs and generated reports needed for reproduction.",
                "- Root-level wrappers for fast validation and one-command VM-backed runs.",
                "",
                "## Reviewer-facing commands",
                "",
                "- `bash run_review_check.sh`: fast paper-claim validation.",
                "- `./artifact/setup.sh && ./artifact/run.sh && ./artifact/validate.sh`:",
                "  minimal working example for repository-local execution.",
                "- `bash run_vm_backed_campaign.sh 0.c0011`: smallest VM-backed baseline.",
                "- `bash run_vm_backed_campaign.sh 0.shadowray`: VM-backed run with a declared step-conditioned SUT overlay.",
                "",
                "## Excluded on purpose",
                "",
                "- Local `.vagrant/` state.",
                "- QEMU runtime overlays and cached base images.",
                "- Generated cloud-init runtime artifacts.",
                "- Developer-local Caldera config at `measurement/sut/caldera_conf/local.yml`.",
                "- Developer-local `.env` and `measurement/meta/` residue.",
                "- Raw `results/evidence`, `results/frozen`, and `release/evidence` trees.",
                "- Python caches and local scratch files.",
                "",
                "The goal is a complete public artifact for reproduction and inspection,",
                "without publishing heavyweight local VM state or developer-only residue.",
                "",
            ]
        ),
    )

    write_text(
        dest_root / "README.md",
        "\n".join(
            [
                "# STICKS Public Artifact",
                "",
                "This repository is the complete public artifact for the STICKS",
                "environment-semantics study.",
                "",
                "It retains three reviewer-facing layers:",
                "",
                "- a fast paper-claim validation path;",
                "- a repository-local minimal working example;",
                "- a broader VM-backed path for campaign/SUT realism checks.",
                "",
                "## Fast reviewer path",
                "",
                "```bash",
                f"git clone {PUBLISHED_REPOSITORY}.git",
                "cd sticks",
                "bash run_review_check.sh",
                "```",
                "",
                "This path reruns the measurement pipeline, refreshes the released",
                "paper-facing outputs, and checks that the synthesized values remain",
                "consistent from the same checkout.",
                "",
                "## Minimal working example",
                "",
                "```bash",
                "./artifact/setup.sh",
                "./artifact/run.sh",
                "./artifact/validate.sh",
                "```",
                "",
                "This is the smallest repository-local execution trace. It is useful",
                "when reviewers want a lightweight run that still exercises campaign",
                "execution and evidence generation directly.",
                "",
                "## VM-backed path",
                "",
                "```bash",
                "bash run_vm_backed_campaign.sh 0.c0011",
                "bash run_vm_backed_campaign.sh 0.shadowray",
                "```",
                "",
                "That path delegates to `scripts/run_lab_campaign.py`, which resolves the",
                "campaign SUT profile, brings up the required VM substrate, applies the",
                "declared base SUT profile, applies step-conditioned overlays for",
                "selected techniques, executes the campaign, regenerates evidence and",
                "synthesized reports, and tears the lab down.",
                "",
                "## Publication contract",
                "",
                "- The fast reviewer path is the primary reproducibility promise.",
                "- The `artifact/` path is the minimal working example for reviewers who",
                "  want the smallest repository-local execution trace.",
                "- The VM-backed path is included for complete public reproduction and",
                "  realism inspection, but should still be interpreted campaign by",
                "  campaign rather than as a blanket historical replay guarantee.",
                "- Heavy local VM images, overlays, and developer-only config are excluded",
                "  on purpose; they are regenerated or provisioned by the included helpers.",
                "- Raw frozen evidence is not bundled; the included scripts regenerate",
                "  reviewer-visible evidence and summaries from a clean checkout.",
                "",
                "## Runtime expectations",
                "",
                "- Fast reviewer path: Python 3.11+, TeX with `latexmk`/`pdflatex`, and",
                "  Poppler tools (`pdftoppm`, `pdfinfo`) on `PATH`.",
                "- Minimal working example: Python 3.11+ only; optional Vagrant/QEMU checks",
                "  are advisory in `artifact/setup.sh`.",
                "- VM-backed path: Vagrant plus a supported provider (`libvirt` on Linux,",
                "  `qemu` on macOS ARM64, or `virtualbox` where stable).",
                "- Recommended representative realism runs:",
                "  `bash run_vm_backed_campaign.sh 0.c0011` or",
                "  `bash run_vm_backed_campaign.sh 0.shadowray`.",
                "",
            ]
        ),
    )


def stage(dest_root: Path) -> None:
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    stage_root(dest_root)
    write_repo_docs(dest_root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage a complete sanitized public repo for the STICKS artifact."
    )
    parser.add_argument(
        "--dest",
        default=str(DEFAULT_DEST),
        help="Destination directory for the staged public repo.",
    )
    args = parser.parse_args()
    dest_root = Path(args.dest).resolve()
    stage(dest_root)
    print(f"[OK] Staged complete public repo at {dest_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
