#!/usr/bin/env python3
"""
Audit the public repository surface for publication blockers.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_JSON = PROJECT_ROOT / "results" / "public_surface_report.json"
OUTPUT_MD = PROJECT_ROOT / "results" / "PUBLIC_SURFACE_REPORT.md"
PAPER_MACROS = PROJECT_ROOT / "release" / "paper_macros.tex"

REQUIRED_PATHS = [
    "run_review_check.sh",
    "run_vm_backed_campaign.sh",
    "README.md",
    "REVIEWER_GUIDE.md",
    "REPRODUCIBILITY.md",
    "MANIFEST.md",
    "ARCHITECTURE.md",
    "PUBLIC_REPOSITORY_SCOPE.md",
    "CONTROLLED_COMPARISON.md",
    "scripts/reproduce.py",
    "scripts/validate_controlled_comparison.py",
    "scripts/evaluate_blind_oracle.py",
    "scripts/verify_claims.py",
    "release/claims/ledger.json",
    "release/claims/evidence_sha256.json",
    "release/experiments/substitution/corpus.json",
    "artifact/setup.sh",
    "artifact/run.sh",
    "artifact/validate.sh",
    "scripts/run_campaign.py",
    "scripts/generate_tables.py",
    "scripts/run_lab_campaign.py",
]

STAGED_REQUIRED_PATHS = [
    "PUBLIC_TREE_SHA256.json",
    "requirements.lock",
    "scripts/public_tree_manifest.py",
    "scripts/verify_enterprise_plan_reproduction.py",
    "release/plans/enterprise/index.json",
]

FORBIDDEN_STAGED_PATHS = [
    "build_artifacts/main.pdf",
    "paper/build_artifacts/main.pdf",
    "release/CLAIMS_EVIDENCE_MATRIX.md",
    "release/claims_evidence_matrix.json",
    "release/CLAIMS_FOR_PAPER.md",
    "release/PAPER_READY_SUMMARY.md",
    "release/CLAIM_EVIDENCE_TRACEABILITY.md",
    "release/claim_evidence_traceability.json",
    "release/COVERAGE_MATRIX.md",
    "release/coverage_matrix.json",
    "release/performance_metrics.tex",
    "release/realism_analysis_report.json",
    "release/reproducibility_package.json",
    "release/CAMPAIGN_SUT_FIDELITY_MATRIX.md",
    "release/campaign_sut_fidelity_matrix.json",
    "release/MITRE_SCOPE_AND_REALISM.md",
    "release/INFRA_AUTOMATION_COVERAGE.md",
    "release/infra_automation_coverage.json",
    "release/fidelity_report.json",
    "release/fidelity_tables.tex",
    "release/full_lab_status_table.tex",
    "release/campaign_results_consolidated.json",
    "release/campaign_results_table.tex",
    "release/paper_ready_macros.tex",
    "release/separated_corpus_results.json",
    "release/separated_corpus_tables.tex",
    "results/CLAIMS_FOR_PAPER.md",
    "results/PAPER_READY_SUMMARY.md",
    "results/CLAIM_EVIDENCE_TRACEABILITY.md",
    "results/claim_evidence_traceability.json",
]

SENSITIVE_PATHS = [
    "measurement/.env",
    "measurement/meta",
    "results/evidence",
    "results/frozen",
]

LEGACY_CALDERA_RUNNERS = {
    "measurement/sut/scripts/run_campaign.py",
    "measurement/sut/scripts/run_finite.py",
}

PUBLIC_DOCS = [
    "README.md",
    "REVIEWER_GUIDE.md",
    "REPRODUCIBILITY.md",
    "ARCHITECTURE.md",
    "PUBLIC_REPOSITORY_SCOPE.md",
    "CONTROLLED_COMPARISON.md",
    "measurement/sut/README.md",
    "measurement/sut/README_REPRODUCIBILITY.md",
    "measurement/sut/CLAIMS_TO_EVIDENCE.md",
    "measurement/sut/FINAL_REVIEW_READINESS.md",
    "measurement/sut/PUBLICATION_CHECKLIST.md",
    "README_MULTI_VM.md",
    "docs/README.md",
    "docs/reproducibility.md",
    "docs/reviewer_quickstart.md",
    "docs/README_REALISTIC.md",
]

FORBIDDEN_SNIPPETS = [
    "main.py init",
    "lib/run_campaign.py",
    "Caldera 5.3.0",
    "Apple Silicon M4 Max",
    "3-VM Caldera Setup",
    "sticks/vagrant",
    "8/8 techniques successful",
    "fully isolated virtual testbed",
]

# Venue names, submission vocabulary and retired review-artifact identifiers, stored as
# BLAKE2b-64 digests of one token or a two-token phrase so the gate never names them.
ADMINISTRATIVE_TERM_DIGESTS = frozenset({
    "f99b60544109131b", "6abb237e042beeb1", "2bd2e89df314690e", "35761706649dfae9",
    "e2d1a66b4bbcd176", "ef07ec9ae38539e0", "443ca6e9b967b7fc", "7084f2296a863a84",
    "c65be06972bc44e0", "d084ce99e0f80a0d", "fca7e0a67e0df247", "5130d41c1fa99469",
    "a393b7f69e9b2fd8", "4b17966e631f798a", "026d8cd4ef2c656d", "6b198f90d1af0517",
    "f3353b5558ad8c26", "2c0305ba00de25c7", "36a075564c31102a", "9e86c3249a8c8180",
})
TERM_TOKEN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9&.\-]*[A-Za-z0-9])?")
# Vendored third-party datasets quote paper citations verbatim and are exempt.
THIRD_PARTY_DATA_PREFIXES = (
    "data/stix/",
    "measurement/sut/scripts/data/",
)


def term_digest(term: str) -> str:
    return hashlib.blake2b(term.encode("utf-8"), digest_size=8).hexdigest()


def contains_administrative_term(text: str) -> bool:
    tokens = TERM_TOKEN.findall(text)
    phrases = (f"{first} {second}" for first, second in zip(tokens, tokens[1:]))
    return any(term_digest(gram) in ADMINISTRATIVE_TERM_DIGESTS for gram in (*tokens, *phrases))


def home_path_snippets(home: Path) -> list[str]:
    """Keep named home paths private without flagging generic /root text."""
    return [] if home == Path("/root") else [str(home)]


SENSITIVE_TEXT_SNIPPETS = home_path_snippets(Path.home())
LAB_PROFILE_PRIVATE_KEY_HEADER = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)

SENSITIVE_TEXT_PATTERNS = {
    "OpenAI/Anthropic secret-key token": re.compile(
        r"\bsk-(?:proj-|ant-api\d{2}-)[A-Za-z0-9_-]{20,}"
    ),
    "GitHub personal-access token": re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    "author workspace path": re.compile(
        r"/(?:Users|home)/[A-Za-z0-9._-]+/(?:arena|paper measurement|autosut)/"
    ),
    "private-key material": re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s+[A-Za-z0-9+/=\s]+"
        r"-----END [A-Z ]*PRIVATE KEY-----"
    ),
}

SENSITIVE_FILE_PATTERNS = (
    re.compile(r"^\.env(?:\..+)?$"),
    re.compile(r"^config(?:\.[^.]+)*\.local\.json$"),
    re.compile(r"^(?:id_rsa|id_ed25519)$"),
    re.compile(r".*(?:private|secret|lab_key).*\.(?:key|pem)$"),
)

TEXT_EXTENSIONS = {
    ".cfg",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".rb",
    ".sh",
    ".tex",
    ".toml",
    ".txt",
    ".tsv",
    ".yaml",
    ".yml",
}

TEXT_FILENAMES = {
    "Vagrantfile",
}

LOCAL_RUNTIME_ARTIFACTS = [
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "src/executors/__pycache__",
    "src/loaders/__pycache__",
    "tests/__pycache__",
    "lab/vagrant/.vagrant",
    "measurement/sut/.vagrant",
    "cloud-init/seed.iso",
    "cloud-init/run-overlay.qcow2",
    "cloud-init/vars.fd",
    "cloud-init/meta-data",
    "cloud-init/user-data",
    "cloud-init/iso-root",
    "run-overlay.qcow2",
    "vars.fd",
    "edk2-aarch64-code.fd",
    "sticks-arm64-qemu.box",
    "sticks-simple.box",
    "sticks-box",
    "sticks-box-simple",
    "evidence/qemu-base",
    "evidence/qemu-multi",
    "results/exploratory",
    "removed_reports",
]

STRUCTURE_SMELLS = [
    "docs/docs",
    "docs/artifact_guide",
    "docs/reproducibility",
    "lab/qeu",
]


def existing_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if (PROJECT_ROOT / path).exists()]


def missing_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if not (PROJECT_ROOT / path).exists()]


def find_forbidden_hits() -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for relative_path in PUBLIC_DOCS:
        path = PROJECT_ROOT / relative_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for snippet in FORBIDDEN_SNIPPETS:
            if snippet in text:
                hits.append({"path": relative_path, "snippet": snippet})
    return hits


def find_sensitive_text_hits() -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path in {OUTPUT_JSON, OUTPUT_MD, Path(__file__).resolve()}:
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS and path.name not in TEXT_FILENAMES:
            continue
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        # The public surface is the tracked surface: a gitignored file never ships, so it
        # cannot leak. Skipping it keeps this scan consistent with the runtime-artifact and
        # structure-smell checks, which already defer to is_git_ignored.
        if is_local_runtime_path(relative_path) or is_git_ignored(relative_path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if relative_path in LEGACY_CALDERA_RUNNERS:
            module = ast.parse(text, filename=relative_path)
            if any(
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "PASSWORD"
                    for target in node.targets
                )
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                for node in module.body
            ):
                hits.append({
                    "path": relative_path,
                    "snippet": "embedded legacy Caldera password",
                })
        for snippet in SENSITIVE_TEXT_SNIPPETS:
            if snippet in text:
                hits.append({"path": relative_path, "snippet": snippet})
        for label, pattern in SENSITIVE_TEXT_PATTERNS.items():
            if pattern.search(text):
                hits.append({"path": relative_path, "snippet": label})
        if relative_path.startswith("lab/sut_profiles/") and LAB_PROFILE_PRIVATE_KEY_HEADER.search(text):
            hits.append({"path": relative_path, "snippet": "lab profile private key"})
        if not relative_path.startswith(THIRD_PARTY_DATA_PREFIXES) and contains_administrative_term(text):
            hits.append({"path": relative_path, "snippet": "venue or submission term"})
    return hits


def is_local_runtime_path(relative_path: str) -> bool:
    parts = Path(relative_path).parts
    return any(part in {".venv", ".pytest_cache", ".vagrant", "__pycache__"} for part in parts)


def find_sensitive_file_hits() -> list[str]:
    hits: list[str] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        if is_local_runtime_path(relative_path) or is_git_ignored(relative_path):
            continue
        if any(pattern.fullmatch(path.name) for pattern in SENSITIVE_FILE_PATTERNS):
            hits.append(relative_path)
    return sorted(hits)


def _paper_macro(name: str) -> str | None:
    if not PAPER_MACROS.is_file():
        return None
    match = re.search(
        rf"\\newcommand\{{\\{re.escape(name)}\}}\{{([^}}]+)\}}",
        PAPER_MACROS.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else None


def find_readme_metric_mismatches() -> list[str]:
    """Reject stale headline values in the reviewer-facing README."""

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    expected = {
        "corpusCampaignCount": _paper_macro("corpusCampaignCount"),
        "corpusStepCount": _paper_macro("corpusStepCount"),
        "corpusSupportedSteps": _paper_macro("corpusSupportedSteps"),
        "corpusCoveragePct": _paper_macro("corpusCoveragePct"),
    }
    if any(value is None for value in expected.values()):
        return ["release/paper_macros.tex is missing a README headline macro"]

    normalized_readme = re.sub(r"\s+", " ", readme.replace(",", ""))
    required_fragments = {
        "corpusCampaignCount": f"{expected['corpusCampaignCount']} campaigns",
        "corpusStepCount": f"{expected['corpusStepCount']} steps",
        "corpusSupportedSteps": f"{expected['corpusSupportedSteps']} catalog-supported steps",
        "coverageRatio": (
            f"{expected['corpusSupportedSteps']} of {expected['corpusStepCount']} "
            f"corpus steps ({expected['corpusCoveragePct']}%)"
        ),
    }
    return [
        f"README.md does not contain generated {label}: {fragment!r}"
        for label, fragment in required_fragments.items()
        if fragment not in normalized_readme
    ]


def is_git_ignored(relative_path: str) -> bool:
    if shutil.which("git") is None:
        return False
    result = subprocess.run(
        ["git", "check-ignore", relative_path],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def split_runtime_artifacts(paths: list[str]) -> tuple[list[str], list[str]]:
    ignored: list[str] = []
    blockers: list[str] = []
    for path in paths:
        if is_local_runtime_path(path) or is_git_ignored(path):
            ignored.append(path)
        else:
            blockers.append(path)
    return ignored, blockers


def split_structure_smells(paths: list[str]) -> tuple[list[str], list[str]]:
    ignored: list[str] = []
    blockers: list[str] = []
    for path in paths:
        if is_git_ignored(path):
            ignored.append(path)
        else:
            blockers.append(path)
    return ignored, blockers


def build_report() -> dict:
    staged = (PROJECT_ROOT / "PUBLIC_TREE_SHA256.json").is_file()
    required_paths = REQUIRED_PATHS + (STAGED_REQUIRED_PATHS if staged else [])
    required_missing = missing_paths(required_paths)
    forbidden_staged_paths = existing_paths(FORBIDDEN_STAGED_PATHS) if staged else []
    sensitive_paths = existing_paths(SENSITIVE_PATHS)
    runtime_paths = existing_paths(LOCAL_RUNTIME_ARTIFACTS)
    ignored_runtime_paths, blocker_paths = split_runtime_artifacts(runtime_paths)
    structure_smells = existing_paths(STRUCTURE_SMELLS)
    ignored_structure_smells, blocker_structure_smells = split_structure_smells(structure_smells)
    forbidden_hits = find_forbidden_hits()
    sensitive_text_hits = find_sensitive_text_hits()
    sensitive_file_hits = find_sensitive_file_hits()
    readme_metric_mismatches = find_readme_metric_mismatches()

    return {
        "schema_version": "2",
        "required_paths_checked": required_paths,
        "missing_required_paths": required_missing,
        "forbidden_staged_paths_present": forbidden_staged_paths,
        "sensitive_paths_present": sensitive_paths,
        "forbidden_text_hits": forbidden_hits,
        "sensitive_text_hits": sensitive_text_hits,
        "sensitive_files_present": sensitive_file_hits,
        "readme_metric_mismatches": readme_metric_mismatches,
        "ignored_local_runtime_artifacts": ignored_runtime_paths,
        "local_runtime_artifacts_present": blocker_paths,
        "ignored_structure_smells": ignored_structure_smells,
        "structure_smells_present": blocker_structure_smells,
        "status": (
            "clean"
            if not required_missing
            and not forbidden_staged_paths
            and not sensitive_paths
            and not forbidden_hits
            and not sensitive_text_hits
            and not sensitive_file_hits
            and not readme_metric_mismatches
            and not blocker_paths
            and not blocker_structure_smells
            else "needs_attention"
        ),
    }


def write_markdown(report: dict) -> None:
    lines = [
        "# Public Surface Report",
        "",
        f"- Status: `{report['status']}`",
        "",
        "## Missing Required Paths",
        "",
    ]

    if report["missing_required_paths"]:
        lines.extend(f"- `{path}`" for path in report["missing_required_paths"])
    else:
        lines.append("- None")

    lines.extend(["", "## Sensitive Paths Present", ""])
    if report["sensitive_paths_present"]:
        lines.extend(f"- `{path}`" for path in report["sensitive_paths_present"])
    else:
        lines.append("- None")

    lines.extend(["", "## Forbidden Staged Paths Present", ""])
    if report["forbidden_staged_paths_present"]:
        lines.extend(f"- `{path}`" for path in report["forbidden_staged_paths_present"])
    else:
        lines.append("- None")

    lines.extend(["", "## Forbidden Text Hits", ""])
    if report["forbidden_text_hits"]:
        for hit in report["forbidden_text_hits"]:
            lines.append(f"- `{hit['path']}` contains `{hit['snippet']}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Sensitive Text Hits", ""])
    if report["sensitive_text_hits"]:
        for hit in report["sensitive_text_hits"]:
            lines.append(f"- `{hit['path']}` contains `{hit['snippet']}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Sensitive Files Present", ""])
    if report["sensitive_files_present"]:
        lines.extend(f"- `{path}`" for path in report["sensitive_files_present"])
    else:
        lines.append("- None")

    lines.extend(["", "## README Metric Mismatches", ""])
    if report["readme_metric_mismatches"]:
        lines.extend(f"- {item}" for item in report["readme_metric_mismatches"])
    else:
        lines.append("- None")

    lines.extend(["", "## Local Runtime Artifacts Present", ""])
    if report["local_runtime_artifacts_present"]:
        lines.extend(f"- `{path}`" for path in report["local_runtime_artifacts_present"])
    else:
        lines.append("- None")

    lines.extend(["", "## Ignored Local Runtime Artifacts", ""])
    if report["ignored_local_runtime_artifacts"]:
        lines.extend(f"- `{path}`" for path in report["ignored_local_runtime_artifacts"])
    else:
        lines.append("- None")

    lines.extend(["", "## Structure Smells Present", ""])
    if report["structure_smells_present"]:
        lines.extend(f"- `{path}`" for path in report["structure_smells_present"])
    else:
        lines.append("- None")

    lines.extend(["", "## Ignored Structure Smells", ""])
    if report["ignored_structure_smells"]:
        lines.extend(f"- `{path}`" for path in report["ignored_structure_smells"])
    else:
        lines.append("- None")

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main(*, write_reports: bool = True) -> None:
    report = build_report()
    if write_reports:
        OUTPUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
        write_markdown(report)
        print(f"Wrote {OUTPUT_JSON}")
        print(f"Wrote {OUTPUT_MD}")
    else:
        print(f"Public surface status: {report['status']}")
    if report["status"] != "clean":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    arguments = parser.parse_args()
    main(write_reports=not arguments.check_only)
