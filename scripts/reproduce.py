#!/usr/bin/env python3
"""Reproduce the STICKS evidence: regenerate every frozen artifact and run the tests.

Reviewer entry point. After `pip install -r requirements.txt`, run
`python scripts/reproduce.py` from the artifact root. It regenerates each frozen evidence
record and table from the tracked inputs, then runs the test suite. Lab-dependent tests
skip when the lab evidence is absent; everything else runs offline with no API keys.

Failures are not masked: a failing step raises and stops the run.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TYPED_EVIDENCE_PATH = PROJECT_ROOT / "typed-run-evidence/c0010-c0026.tar.gz"
TYPED_REFERENCE_MANIFEST_PATH = (
    PROJECT_ROOT / "typed-run-evidence/reference-public-tree-4c52b4e.json"
)
TYPED_BOUND_REFERENCE_MANIFEST_PATH = (
    PROJECT_ROOT / "typed-run-evidence/reference-run-source-tree.json"
)
CALDERA_EVIDENCE_PATH = PROJECT_ROOT / "typed-run-evidence/caldera-c0026.tar.gz"
CALDERA_C0010_EVIDENCE_PATH = PROJECT_ROOT / "typed-run-evidence/caldera-c0010.tar.gz"
CALDERA_C0010_REFERENCE_PATH = PROJECT_ROOT / "typed-run-evidence/caldera-c0010-reference-run-source-tree.json"
CALDERA_BOUND_REFERENCE_MANIFEST_PATH = (
    PROJECT_ROOT / "typed-run-evidence/caldera-reference-run-source-tree.json"
)
C0045_SERIES_ARCHIVE_PATH = (
    PROJECT_ROOT / "release/experiments/c0045_compute_effect_series/series.tar.gz"
)

# Regenerate frozen evidence, then render the tables that read it.
BUILD_STEPS = [
    "verify_enterprise_plan_reproduction.py",
    "build_deep_concretization.py",
    "build_corpus_characterization_evidence.py",
    "build_behavioral_structure_evidence.py",
    "build_lateral_movement_grounding_evidence.py",
    "build_lateral_movement_adjudication.py",
    "build_substitution_corpus_evidence.py",
    "build_derived_environment_evidence.py",
    "build_unconstrained_divergence_evidence.py",
    "build_provenance_evidence.py",
    "build_enrichment_baseline_evidence.py",
    "build_execution_commitments_evidence.py",
    "build_procedural_behavior_comparison.py",
    "build_behavioral_substitution_evidence.py",
    "build_admission_safety_evidence.py",
    "build_evidence_policy_report.py",
    "build_contract_strength_report.py",
    "build_proposal_containment_evidence.py",
    "build_enumeration_scaling_evidence.py",
    "build_attack_flow_interop_evidence.py",
    "build_execution_locus_evidence.py",
    "build_catalog_baseline_evidence.py",
    "build_stage2_authoring_evidence.py",
    "build_authoring_cost_evidence.py",
    "build_linux_discovery_evidence.py",
]

# Regenerated only with local models, so they stay out of the offline pipeline above:
#   python scripts/build_proposer_convergence_evidence.py       (needs an Ollama endpoint)
#   python scripts/collect_unconstrained_reconstructions.py     (needs an Ollama endpoint)
# The divergence metric itself is deterministic and runs offline from the frozen
# reconstructions; only their collection needs the models. The frozen records are the
# recorded outcome for reviewers without the models.
LOCAL_MODEL_STEPS = [
    "build_proposer_convergence_evidence.py",
    "collect_unconstrained_reconstructions.py",
]
RENDER_STEPS = [
    "render_provenance_table.py",
    "render_enrichment_baseline_table.py",
    "render_execution_commitments_table.py",
    "render_claim_ledger_table.py",
    "render_admission_comparison_table.py",
    "build_fidelity_rationale.py",
    "render_paper_macros.py",
]

# Runs last: every asserted claim must still reach frozen evidence after regeneration.
AUDIT_STEPS = ["check_public_surface.py"]
TYPED_OUTCOMES_INPUT = re.compile(
    r"\\input\s*\{\s*results/typed_campaign_outcomes\.tex\s*\}"
)
CALDERA_OUTCOMES_INPUT = re.compile(
    r"\\input\s*\{\s*results/caldera_campaign_outcomes\.tex\s*\}"
)
C0045_MACROS_INPUT = re.compile(
    r"\\input\s*\{\s*results/c0045_series_macros\.tex\s*\}"
)


def _verify_public_tree_if_present() -> None:
    manifest = PROJECT_ROOT / "PUBLIC_TREE_SHA256.json"
    if manifest.is_file():
        _run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "public_tree_manifest.py"),
                "verify",
                "--root",
                str(PROJECT_ROOT),
                "--manifest",
                str(manifest),
            ]
        )


def _run(args: list[str]) -> None:
    print(f"$ {' '.join(args)}")
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(PROJECT_ROOT / "src"), str(PROJECT_ROOT), environment.get("PYTHONPATH", ""))
    )
    subprocess.run(args, cwd=PROJECT_ROOT, check=True, env=environment)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manuscript",
        type=Path,
        help="also audit this LaTeX manuscript against the claim ledger",
    )
    return parser.parse_args()


def _manuscript_inputs(manuscript: Path, pattern: re.Pattern[str]) -> bool:
    source = manuscript.read_text(encoding="utf-8")
    active_lines = (line.split("%", 1)[0] for line in source.splitlines())
    return pattern.search("\n".join(active_lines)) is not None


def _manuscript_requires_typed_evidence(manuscript: Path) -> bool:
    return _manuscript_inputs(manuscript, TYPED_OUTCOMES_INPUT)


def _require_manuscript_evidence(manuscript: Path | None) -> None:
    if manuscript is None or not _manuscript_requires_typed_evidence(manuscript):
        return
    if not TYPED_EVIDENCE_PATH.is_file():
        raise FileNotFoundError(
            "Manuscript cites typed QEMU outcomes, but the typed-run evidence archive "
            f"is missing: {TYPED_EVIDENCE_PATH}"
        )


def _verify_c0045_paper_macros(manuscript: Path | None) -> None:
    """Re-render the C0045 macros from the archive and require the paper's copy."""
    if manuscript is None or not _manuscript_inputs(manuscript, C0045_MACROS_INPUT):
        return
    if not C0045_SERIES_ARCHIVE_PATH.is_file():
        raise FileNotFoundError(
            "Manuscript cites the C0045 observer calibration, but its archive "
            f"is missing: {C0045_SERIES_ARCHIVE_PATH}"
        )
    rendered = subprocess.run(
        [sys.executable, "-m", "scripts.render_c0045_series_macros",
         "--archive", str(C0045_SERIES_ARCHIVE_PATH)],
        cwd=PROJECT_ROOT, check=True, capture_output=True, text=True,
    ).stdout
    paper_copy = manuscript.parent / "results/c0045_series_macros.tex"
    if paper_copy.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"{paper_copy} differs from the C0045 archive")


def _verify_caldera_evidence(manuscript: Path | None) -> None:
    """Screen and replay the C0026 cycle dispatched through CALDERA."""
    cited = manuscript is not None and _manuscript_inputs(
        manuscript, CALDERA_OUTCOMES_INPUT
    )
    if not CALDERA_EVIDENCE_PATH.is_file():
        if cited:
            raise FileNotFoundError(
                "Manuscript cites the CALDERA C0026 cycle, but its archive "
                f"is missing: {CALDERA_EVIDENCE_PATH}"
            )
        return
    _run([
        sys.executable, "-m", "scripts.screen_typed_evidence_privacy",
        "--archive", str(CALDERA_EVIDENCE_PATH), "--series", "caldera",
        "--bound-reference-manifest", str(CALDERA_BOUND_REFERENCE_MANIFEST_PATH),
    ])
    command = [
        sys.executable, "-m", "scripts.verify_typed_evidence_archive",
        "--archive", str(CALDERA_EVIDENCE_PATH), "--series", "caldera",
    ]
    if cited:
        command.extend([
            "--paper-outcomes",
            str(manuscript.parent / "results/caldera_campaign_outcomes.tex"),
        ])
    _run(command)


def _verify_c0010_caldera_evidence() -> None:
    if not CALDERA_C0010_EVIDENCE_PATH.is_file():
        return
    _run([
        sys.executable, "-m", "scripts.screen_typed_evidence_privacy",
        "--archive", str(CALDERA_C0010_EVIDENCE_PATH), "--series", "caldera-c0010",
        "--bound-reference-manifest", str(CALDERA_C0010_REFERENCE_PATH),
    ])
    _run([
        sys.executable, "-m", "scripts.verify_typed_evidence_archive",
        "--archive", str(CALDERA_C0010_EVIDENCE_PATH), "--series", "caldera-c0010",
    ])


def _verify_c0045_series_if_present() -> None:
    if C0045_SERIES_ARCHIVE_PATH.is_file():
        _run([
            sys.executable,
            "-m",
            "scripts.verify_c0045_effect_series_archive",
            "--archive",
            str(C0045_SERIES_ARCHIVE_PATH),
        ])
        _run([
            sys.executable,
            "-m",
            "scripts.screen_c0045_series_privacy",
            "--archive",
            str(C0045_SERIES_ARCHIVE_PATH),
        ])


def _typed_reference_args() -> list[str]:
    if TYPED_BOUND_REFERENCE_MANIFEST_PATH.is_file():
        return ["--bound-reference-manifest", str(TYPED_BOUND_REFERENCE_MANIFEST_PATH)]
    if TYPED_REFERENCE_MANIFEST_PATH.is_file():
        return ["--known-reference-manifest", str(TYPED_REFERENCE_MANIFEST_PATH)]
    return ["--reference-root", str(PROJECT_ROOT)]


def main() -> int:
    args = _parse_args()
    sys.dont_write_bytecode = True

    _require_manuscript_evidence(args.manuscript)

    _verify_public_tree_if_present()

    for script in BUILD_STEPS + RENDER_STEPS:
        command = [sys.executable, str(SCRIPTS_DIR / script)]
        if script == "build_enumeration_scaling_evidence.py":
            command.append("--no-timing-output")
        _run(command)

    claim_command = [sys.executable, str(SCRIPTS_DIR / "verify_claims.py")]
    if args.manuscript is not None:
        claim_command.extend(["--manuscript", str(args.manuscript.resolve())])
    _run(claim_command)

    _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "-q",
            "-p",
            "no:cacheprovider",
        ]
    )
    for script in AUDIT_STEPS:
        _run([sys.executable, str(SCRIPTS_DIR / script), "--check-only"])
    if TYPED_EVIDENCE_PATH.is_file():
        _run([
            sys.executable,
            "-m",
            "scripts.screen_typed_evidence_privacy",
            "--archive",
            str(TYPED_EVIDENCE_PATH),
            *_typed_reference_args(),
        ])
        archive_command = [
            sys.executable,
            "-m",
            "scripts.verify_typed_evidence_archive",
            "--archive",
            str(TYPED_EVIDENCE_PATH),
        ]
        if args.manuscript is not None and _manuscript_requires_typed_evidence(
            args.manuscript
        ):
            archive_command.extend(
                [
                    "--paper-outcomes",
                    str(args.manuscript.parent / "results/typed_campaign_outcomes.tex"),
                ]
            )
        _run(archive_command)
    _verify_caldera_evidence(args.manuscript)
    _verify_c0010_caldera_evidence()
    _verify_c0045_series_if_present()
    _verify_c0045_paper_macros(args.manuscript)
    _verify_public_tree_if_present()
    print("[reproduce] evidence regenerated, claims verified, and tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
