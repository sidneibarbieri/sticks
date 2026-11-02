"""Stage and validate the reviewer-facing STICKS repository.

The primary package is the deterministic procedural-admission artifact. Older
measurement and VM experiments remain available as a clearly secondary layer,
but local runtime state, host traces, keys, and developer configuration never
enter the staged repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

STICKS_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(STICKS_ROOT / "src"), str(STICKS_ROOT))
PAPER_AUTHORING_RUNS = tuple(json.loads(
    (STICKS_ROOT / "release" / "experiments" / "stage2_authoring" / "paper_runs.json").read_text(encoding="utf-8")
)["run_ids"])
PUBLIC_COMPARISON_ENTRIES = frozenset({
    "2026-09-07-local",
    "2026-09-07-qwen14b",
    "prospective-qwen36-p17-v5-20261023",
    "qualification_status.json",
})
DEFAULT_DEST = STICKS_ROOT.parent / "release-staging" / "sticks-artifact"
TYPED_EVIDENCE_PATH = Path("typed-run-evidence/c0010-c0026.tar.gz")
TYPED_REFERENCE_MANIFEST_PATH = Path(
    "typed-run-evidence/reference-public-tree-4c52b4e.json"
)
CALDERA_EVIDENCE_PATH = Path("typed-run-evidence/caldera-c0026.tar.gz")
CALDERA_REFERENCE_MANIFEST_PATH = Path(
    "typed-run-evidence/caldera-reference-run-source-tree.json"
)
TYPED_BOUND_REFERENCE_MANIFEST_PATH = Path(
    "typed-run-evidence/reference-run-source-tree.json"
)
C0045_SERIES_ARCHIVE_PATH = Path(
    "release/experiments/c0045_compute_effect_series/series.tar.gz"
)
REQUIRED_RELEASE_FILES = (
    Path("release/experiments/controlled_comparison/qualification_status.json"),
)

ROOT_FILES = [
    ".gitignore",
    "ARCHITECTURE.md",
    "CONTROLLED_COMPARISON.md",
    "LICENSE",
    "MANIFEST.md",
    "PUBLIC_REPOSITORY_SCOPE.md",
    "README.md",
    "REPRODUCIBILITY.md",
    "REVIEWER_GUIDE.md",
    "THIRD_PARTY_NOTICES.md",
    "THIRD_PARTY_LICENSES/ATTACK_FLOW_APACHE-2.0.txt",
    "THIRD_PARTY_LICENSES/MITRE_CTI_LICENSE.txt",
    "Vagrantfile",
    "apply_sut_profile.py",
    "caldera_manager.py",
    "caldera_mock.py",
    "config.example.json",
    "config.openai.example.json",
    "multi_vm_manager.py",
    "multi_vm_manager_2vm.py",
    "pyproject.toml",
    "pyrightconfig.json",
    "requirements.lock",
    "requirements.txt",
    "requirements-qa.in",
    "requirements-qa.txt",
    "run_review_check.sh",
    "run_vm_backed_campaign.sh",
    "setup.sh",
    "vagrant-multi.sh",
    "vagrant-wrapper.sh",
    "docs/REALIZATION_SPACE.md",
    "docs/RECONSTRUCTION_ARCHITECTURE.md",
    "docs/FACT_SEMANTICS.md",
    "docs/LINUX_DISCOVERY.md",
    "docs/IAC_LIMITATIONS_ARM64.md",
    "docs/reviewer_quickstart.md",
    "docs/caldera_runtime.md",
    "docs/COVERAGE_EVIDENCE_SELECTION.md",
]

ROOT_DIRS = [
    "artifact",
    "campaigns",
    "data",
    "examples/atomic_hostname",
    "infra",
    "lab",
    "measurement",
    "release",
    "results",
    "scripts",
    "src",
    "tests",
    "web",
]

# These unclaimed development experiments are outside the submission snapshot.
EXPERIMENTAL_ONLY_PATHS = frozenset({
    "src/contracts/branch_decision.py",
    "src/runners/conditional_execution.py",
    "scripts/run_conditional_caldera_conformance.py",
    "scripts/verify_conditional_caldera_conformance.py",
    "tests/test_attack_flow_branch_counterexample.py",
    "tests/test_conditional_conformance_agent_trust.py",
    "tests/test_conditional_conformance_cells.py",
    "tests/test_conditional_execution.py",
    "tests/test_conditional_conformance_verifier.py",
})

MEASUREMENT_SUT_INTERNAL_DOCS = {
    "FINAL_REVIEW_READINESS.md",
    "FINAL_STATUS.md",
    "INSPIRED_PROFILES.md",
    "MULTI_TECH_ANALYSIS.md",
    "PROVISIONING_ANALYSIS.md",
    "PUBLICATION_CHECKLIST.md",
    "RESULTS_CLASSIFICATION.md",
    "ROOT_CAUSE_ANALYSIS.md",
    "SCRIPT_ANALYSIS.md",
    "TECHNICAL_ANALYSIS.md",
    "TOP_TIER_REQUIREMENTS.md",
}

COMMON_RUNTIME_NAMES = {
    ".DS_Store",
    ".pytest_cache",
    ".vagrant",
    "__pycache__",
}

RELEASE_ROOT_ALLOWLIST = {
    "claims",
    "enriched",
    "experiments",
    "paper_macros.tex",
    "linux_discovery_macros.tex",
    "admission_macros.tex",
    "fidelity_macros.tex",
    "plans",
}


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_file(source: Path, destination: Path) -> None:
    ensure_parent(destination)
    shutil.copy2(source, destination)


def ignore_for_directory(directory: str):
    directory_path = STICKS_ROOT / directory

    def _ignore(source: str, names: list[str]) -> set[str]:
        source_path = Path(source)
        relative = source_path.relative_to(directory_path)
        ignored = {name for name in names if name in COMMON_RUNTIME_NAMES}
        ignored.update(name for name in names if name.endswith((".pyc", ".pyo")))
        ignored.update(name for name in names if name.endswith(".egg-info"))
        ignored.update(
            name for name in names
            if (Path(directory) / relative / name).as_posix() in EXPERIMENTAL_ONLY_PATHS
        )

        if relative == Path() and directory == "tests":
            ignored.add("internal")

        if relative == Path() and directory == "data":
            # This directory is entirely run-generated. It contains author-host paths,
            # a hostname, and a generated TLS private key, and the primary reproduction
            # does not read it.
            ignored.add("artifacts")

        if relative == Path() and directory == "measurement":
            ignored.update(
                {
                    ".env",
                    "meta",
                    "PUBLISHING_CHECKLIST.md",
                    "GIT_READY_MANIFEST.md",
                    "MEASUREMENT_DOD.md",
                }
            )

        if relative == Path("sut") and directory == "measurement":
            ignored.update(name for name in names if name in MEASUREMENT_SUT_INTERNAL_DOCS)

        if relative == Path("sut/caldera_conf") and directory == "measurement":
            ignored.add("local.yml")

        if relative == Path("sut/scripts") and directory == "measurement":
            ignored.update(
                {
                    "analyze_campaigns.py",
                    "compare_related_work.py",
                    "llm_environment_inference.py",
                    "package_paper2_artifact.py",
                }
            )

        if relative == Path("sut/scripts/results/audit") and directory == "measurement":
            ignored.add("llm")

        if relative == Path("sut/scripts/results") and directory == "measurement":
            ignored.add("rendered_figures")

        if relative == Path("qemu") and directory == "lab":
            ignored.add("runtime")

        if relative == Path("qemu/images") and directory == "lab":
            ignored.update(name for name in names if name.endswith(".img"))

        if relative == Path("provisioning/cloud-init") and directory == "lab":
            ignored.update(
                {
                    "iso-root",
                    "meta-data",
                    "run-overlay.qcow2",
                    "seed.iso",
                    "user-data",
                    "vars.fd",
                }
            )

        if relative == Path() and directory == "scripts":
            ignored.update(
                {
                    "audit_paper_macros.py",
                    "generate_paper_measurements.py",
                    "generate_paper_ready_artifacts.py",
                    "generate_separated_corpus.py",
                    "submission_freeze.sh",
                }
            )

        if relative == Path("executors") and directory == "src":
            ignored.add("simple_working_executors_shadowray.py")

        if relative == Path() and directory == "results":
            # `results/` is run output. No pre-existing report enters the package;
            # the package gate creates only its own public-surface report.
            ignored.update(names)

        if relative == Path() and directory == "release":
            # An allowlist prevents earlier paper-readiness and infrastructure reports
            # from looking authoritative beside the registered claim ledger.
            ignored.update(name for name in names if name not in RELEASE_ROOT_ALLOWLIST)

        if relative == Path("experiments") / "stage2_authoring" / "runs" and directory == "release":
            ignored.update(name for name in names if name not in PAPER_AUTHORING_RUNS)
        if relative == Path("experiments/controlled_comparison") and directory == "release":
            ignored.update(name for name in names if name not in PUBLIC_COMPARISON_ENTRIES)
        if relative == Path("experiments/enumeration_scaling") and directory == "release":
            ignored.add("timing.json")

        return ignored

    return _ignore


def copy_tree(source: Path, destination: Path, directory_name: str) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=ignore_for_directory(directory_name))


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(textwrap.dedent(_resolve_macros(text)).lstrip(), encoding="utf-8")


def _generated_macros() -> dict[str, str]:
    """The manuscript macros, so staged documentation quotes one generated source."""
    macro_path = STICKS_ROOT / "release" / "paper_macros.tex"
    if not macro_path.is_file():
        raise FileNotFoundError(
            f"missing generated macros: {macro_path}; run scripts/render_paper_macros.py"
        )
    return dict(
        re.findall(
            r"\\newcommand\{\\(\w+)\}\{([^}]*)\}", macro_path.read_text(encoding="utf-8")
        )
    )


def _resolve_macros(text: str) -> str:
    """Substitute {{macroName}} placeholders so staged prose cannot drift from evidence."""
    placeholders = set(re.findall(r"\{\{(\w+)\}\}", text))
    if not placeholders:
        return text
    macros = _generated_macros()
    missing = sorted(placeholders - macros.keys())
    if missing:
        raise KeyError(f"staged documentation references unknown macros: {missing}")
    for name in placeholders:
        text = text.replace(f"{{{{{name}}}}}", macros[name])
    return text


def stage_root(destination: Path) -> None:
    for relative in ROOT_FILES:
        source = STICKS_ROOT / relative
        if source.exists():
            copy_file(source, destination / relative)

    for relative in ROOT_DIRS:
        source = STICKS_ROOT / relative
        if source.exists():
            copy_tree(source, destination / relative, relative)


def write_repo_docs(
    destination: Path,
    repository_url: str | None,
    *,
    bundled_typed_evidence: bool = False,
    bundled_typed_reference: bool = False,
    bundled_bound_typed_reference: bool = False,
    bundled_c0045_series: bool = False,
    public_evidence_release: bool = False,
    anonymous_review: bool = False,
) -> None:
    if public_evidence_release and not bundled_typed_evidence:
        raise ValueError("A public evidence release requires a typed evidence archive")
    copy_file(STICKS_ROOT / "run_review_check.sh", destination / "run_review_check.sh")
    (destination / "run_review_check.sh").chmod(0o755)

    repository_line = (
        f"- Repository: `{repository_url}`."
        if repository_url
        else "- Repository URL is supplied by the distribution channel."
    )
    write_text(
        destination / "ARTIFACT_MANIFEST.md",
        f"""
        # Public Artifact Manifest

        {repository_line}

        ## Primary evidence path

        - `scripts/reproduce.py` regenerates every registered experiment record.
        - `release/claims/ledger.json` maps each property to evidence and tests.
        - `release/claims/evidence_sha256.json` freezes evidence and test hashes.
        - `PUBLIC_TREE_SHA256.json` freezes every shipped file outside declared runtime output.
        - `run_review_check.sh` runs regeneration, integrity checks, hygiene, and tests.

        ## Secondary material

        - `measurement/sut/` and the VM/lab helpers preserve earlier experiments.
        - Run the older measurement gate with `bash run_review_check.sh --legacy`.
        - That material is not evidence for a registered property unless the ledger links it.

        ## Excluded

        Local VM state, caches, provider configuration, credentials, private keys,
        unselected runtime evidence, superseded result reports, and derived
        manuscript PDFs are excluded. In particular, `paper/build_artifacts/main.pdf` is
        not reviewer-facing artifact evidence.
        """,
    )

    shutil.copyfile(STICKS_ROOT / "README.md", destination / "README.md")

    write_text(
        destination / "REVIEWER_GUIDE.md",
        """
        # Reviewer Guide

        ## Primary path

        ```bash
        python3 -m venv .venv
        .venv/bin/python -m pip install -r requirements.txt
        bash run_review_check.sh
        ```

        The gate regenerates every registered record, verifies the frozen SHA-256
        manifest, audits claim-to-evidence chains, checks the public surface, and runs
        the packaged tests. It also recompiles all 55 released Enterprise campaign
        plans in a temporary directory and compares their bytes, index, and source
        provenance. A failure is terminal; no step is masked.

        Inspect `release/claims/verification.json`,
        `release/claims/evidence_sha256.json`, `release/experiments/`, and
        `release/paper_macros.tex` after the run.

        ## Manuscript audit

        ```bash
        PAPER_DIR=../paper bash run_review_check.sh
        ```

        This also rejects unregistered references, omitted registered properties,
        blocked claims, forbidden wording, and known unsupported legacy results.

        ## Secondary path

        `bash run_review_check.sh --legacy` runs the retained infrastructure-era
        measurement check. It is not part of the primary claim contract.
        """,
    )

    write_text(
        destination / "REPRODUCIBILITY.md",
        """
        # Reproducibility Contract

        The reproducible unit is a registered property in
        `release/claims/ledger.json`. Each non-blocked property names its population,
        support type, evidence files, tests, permitted wording, and forbidden wording.
        `scripts/reproduce.py` rebuilds the evidence from tracked inputs and verifies
        the frozen evidence manifest. `PUBLIC_TREE_SHA256.json` additionally binds the
        complete staged repository; the reviewer gate verifies it before and after the
        run, excluding only declared runtime reports and caches.

        The primary path requires Python 3.11 or later and `requirements.txt`. It needs
        no network after dependency installation and no API key, container runtime,
        hypervisor, or external service.

        Three populations remain separate: catalog coverage
        ({{corpusSupportedSteps}}/{{corpusStepCount}} steps), deep
        admission evaluation (25 steps in three fully supported campaigns), and
        selected local execution evidence (three T1105 realizations). Retained VM and
        container experiments are secondary compatibility material.

        The two Stage-2 runs selected in
        `release/experiments/stage2_authoring/paper_runs.json` ship with their
        recorded decisions. Other local runs are excluded. The offline path
        rechecks admission, not model generation. The cited runs use a mutable
        model tag and one records a dirty source tree, so they are exploratory
        rather than clean model-reproduction evidence. Their contract-valid
        draft reach is not an executed-effect count.
        """,
    )

    write_text(
        destination / "ARCHITECTURE.md",
        """
        # Architecture

        The primary pipeline (1) compiles a pinned ATT&CK-in-STIX campaign into a typed
        plan, (2) retrieves and enumerates all finite catalog candidates, (3) admits
        candidates against an explicitly scoped fact state, (4) emits a concretized
        plan with provenance and semantic hashes, and (5) certifies selected executions
        against declared effects and evidence predicates.

        A versioned fact registry gives every planning fact a unique semantic identity
        and a closed set of permitted origins. The workbench and Stage 2 controller
        reject a catalog that fails this static check. It is a modeling safeguard, not
        evidence that the corresponding state held in a live environment.

        Proposal and admission are separate. A human or model may propose a template,
        but only the deterministic verifier can commit it. Unknown templates, wrong
        techniques, and unavailable bindings fail admission and leave the plan
        unchanged. Older campaign runners and VM/container helpers form a secondary
        compatibility layer and are not dependencies of the primary evidence path.

        The optional controlled-comparison layer emits a common hash-bound proposal
        record for every arm, removes the arm label before admission, and retains a
        separate assignment record for post-decision reconciliation. Its run ledger
        rejects missing combinations and unverifiable success evidence. This is tested
        experiment infrastructure, not a completed comparison result.
        """,
    )

    write_text(
        destination / "PUBLIC_REPOSITORY_SCOPE.md",
        """
        # Public Repository Scope

        The stable contract is `run_review_check.sh`, `scripts/reproduce.py`, the
        compiler/concretization/contract/evaluation modules, pinned inputs under
        `data/`, frozen records under `release/experiments`, the claim ledger and
        integrity manifest, and linked tests.

        `CONTROLLED_COMPARISON.md` and its validators define an optional reusable
        experiment contract. They support no property until a frozen run set is
        registered in the claim ledger.

        Local configuration, credentials, private keys, generated host traces, caches,
        VM state, unselected runtime evidence, manuscript-administration files, and derived
        manuscript PDFs are excluded.
        Pinned third-party corpora remain byte-preserved. Incidental publication names
        inside source records are corpus content, not artifact targeting; authored
        surfaces remain evaluation-channel neutral.
        `measurement/sut`, `lab`, and older runners are secondary compatibility material.
        """,
    )

    write_text(
        destination / "MANIFEST.md",
        """
        # Manifest

        ## Primary

        - `run_review_check.sh`
        - `scripts/reproduce.py`, `scripts/verify_claims.py`, `scripts/check_public_surface.py`
        - `CONTROLLED_COMPARISON.md`, `scripts/validate_controlled_comparison.py`,
          `scripts/evaluate_blind_oracle.py`
        - `src/compilers/`, `src/concretization/`, `src/contracts/`, `src/evaluation/`
        - `docs/REALIZATION_SPACE.md`, `docs/RECONSTRUCTION_ARCHITECTURE.md`,
          `docs/FACT_SEMANTICS.md`
        - `data/stix/`, `data/concretization/`
        - `release/plans/`, `release/experiments/`, `release/claims/`
        - `PUBLIC_TREE_SHA256.json`
        - `tests/`

        ## Secondary

        - `measurement/sut/`, `lab/`, `artifact/`, older runners, and SUT profiles

        Secondary material supports no manuscript claim unless the ledger links it.
        The controlled-comparison contract supports no result until a frozen experiment
        and complete evidence ledger are registered.
        """,
    )
    if bundled_typed_evidence:
        status = (
            "This release includes the selected archive."
            if public_evidence_release
            else "This selected archive is a private release candidate pending content "
                 "and privacy approval."
        )
        heading = (
            "Typed-run evidence" if public_evidence_release
            else "Private typed-run evidence candidate"
        )
        note = (
            f"\n## {heading}\n\n"
            "`typed-run-evidence/c0010-c0026.tar.gz` is included in the tree manifest "
            "and audited by `run_review_check.sh`. The check screens changed bytes for "
            "recognizable identifiers and secrets, and reports reference-fixture matches "
            f"separately. {status} The audit replays sealed receipts and recorded VM "
            "states; it does not rerun QEMU or certify historical fidelity. Receipt source "
            "hashes identify the archived run source, before the evidence archive and "
            "release metadata were added to this package.\n"
        )
        if bundled_bound_typed_reference:
            note += (
                "The privacy screen compares this archive with the bundled "
                "reference manifest byte-identical to both sealed run workspaces. "
                "The receipts and source manifests are independently verified. "
                "Lexical screening does not replace semantic privacy approval.\n"
            )
        elif bundled_typed_reference:
            note += (
                "The privacy screen compares this exact archive with the bundled "
                "SHA-pinned manifest of the earlier public tree, not with unrelated "
                "changes in this release. It remains a lexical screen; semantic "
                "privacy approval is separate.\n"
            )
        for name in ("README.md", "ARTIFACT_MANIFEST.md", "PUBLIC_REPOSITORY_SCOPE.md"):
            with (destination / name).open("a", encoding="utf-8") as output:
                output.write(note)
    if bundled_c0045_series:
        if anonymous_review:
            heading = "C0045 compute-effect series (anonymous review)"
            status = (
                "The hash-bound semantic review approves this archive for anonymous "
                "review only. Identified release requires separate approval."
            )
        elif public_evidence_release:
            heading = "C0045 compute-effect series"
            status = "This release includes the selected series."
        else:
            heading = "Private C0045 compute-effect series candidate"
            status = (
                "This candidate is pending semantic privacy approval and is not "
                "authorized for public release."
            )
        note = (
            f"\n## {heading}\n\n"
            f"`{C0045_SERIES_ARCHIVE_PATH}` is bound by `PUBLIC_TREE_SHA256.json` "
            "and replayed by `bash run_review_check.sh`. To replay only its "
            "20 selected cells, run `PYTHONPATH=src:. python3 -m "
            "scripts.verify_c0045_effect_series_archive --archive "
            f"{C0045_SERIES_ARCHIVE_PATH}`. The replay checks recorded target "
            "CPU effects and three controls per block; it does not execute a "
            "new QEMU campaign or establish historical ShadowRay fidelity. "
            f"{status}\n"
        )
        for name in (
            "README.md", "REVIEWER_GUIDE.md", "ARTIFACT_MANIFEST.md",
            "PUBLIC_REPOSITORY_SCOPE.md",
        ):
            with (destination / name).open("a", encoding="utf-8") as output:
                output.write(note)


def stage(
    destination: Path,
    repository_url: str | None = None,
    *,
    typed_evidence_archive: Path | None = None,
    typed_evidence_reference_manifest: Path | None = None,
    typed_evidence_bound_reference_manifest: Path | None = None,
    c0045_series_archive: Path | None = None,
    c0045_privacy_review: Path | None = None,
    caldera_evidence_archive: Path | None = None,
    caldera_reference_manifest: Path | None = None,
    caldera_c0010_archive: Path | None = None,
    caldera_c0010_reference: Path | None = None,
    public_evidence_release: bool = False,
    anonymous_review: bool = False,
    identified_release: bool = False,
) -> None:
    for relative_path in REQUIRED_RELEASE_FILES:
        source_path = STICKS_ROOT / relative_path
        if not source_path.is_file():
            raise FileNotFoundError(f"required release status is missing: {relative_path}")
    if anonymous_review and identified_release:
        raise ValueError("A release cannot be both anonymous and identified")
    if anonymous_review and repository_url:
        raise ValueError("Anonymous review candidates cannot record a repository URL")
    if repository_url and not identified_release:
        raise ValueError("A repository URL requires identified_release=True")
    if identified_release and not repository_url:
        raise ValueError("An identified release requires a repository URL")
    if (
        typed_evidence_reference_manifest is not None
        and typed_evidence_bound_reference_manifest is not None
    ):
        raise ValueError("Select one typed evidence reference manifest")
    reference_manifest = (
        typed_evidence_bound_reference_manifest or typed_evidence_reference_manifest
    )
    if reference_manifest is not None and typed_evidence_archive is None:
        raise ValueError("A typed reference manifest requires a typed evidence archive")
    release_candidate = anonymous_review or public_evidence_release or identified_release
    if c0045_privacy_review is not None and c0045_series_archive is None:
        raise ValueError("A C0045 privacy review requires a C0045 series archive")
    if (
        release_candidate
        and c0045_series_archive is not None
        and c0045_privacy_review is None
    ):
        raise ValueError("C0045 series archive requires a privacy review before release")
    if c0045_series_archive is not None and (
        identified_release or (public_evidence_release and not anonymous_review)
    ):
        from runners.c0045_privacy_review import verify_c0045_privacy_review

        if c0045_privacy_review is None or not c0045_privacy_review.is_file():
            raise ValueError("C0045 series is approved only for anonymous review without an identified release record")
        verify_c0045_privacy_review(
            c0045_series_archive, c0045_privacy_review, require_identified=True,
        )
    if (
        release_candidate
        and typed_evidence_archive is not None
        and reference_manifest is None
    ):
        raise ValueError("A release with typed evidence requires a typed evidence reference manifest")
    if release_candidate and typed_evidence_archive is None:
        raise ValueError("A release requires a typed evidence archive for supported claim P26")
    if typed_evidence_archive is not None:
        source = typed_evidence_archive.resolve(strict=True)
        if source.is_relative_to(destination.resolve()):
            raise ValueError("Evidence archive must be outside the destination")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(STICKS_ROOT / "src"), str(STICKS_ROOT), environment.get("PYTHONPATH", ""))
        )
        subprocess.run(
            [sys.executable, "-m", "scripts.verify_typed_evidence_archive", "--archive", str(source)],
            cwd=STICKS_ROOT,
            check=True,
            env=environment,
        )
        if reference_manifest is not None:
            reference_source = reference_manifest.resolve(strict=True)
            if reference_source.is_relative_to(destination.resolve()):
                raise ValueError("Typed reference manifest must be outside the destination")
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.screen_typed_evidence_privacy",
                    "--archive",
                    str(source),
                    "--bound-reference-manifest"
                    if typed_evidence_bound_reference_manifest is not None
                    else "--known-reference-manifest",
                    str(reference_source),
                ],
                cwd=STICKS_ROOT,
                check=True,
                env=environment,
            )
    caldera_sources = []
    for series, supplied_archive, supplied_reference, target_archive, target_reference in (
        ("caldera", caldera_evidence_archive, caldera_reference_manifest,
         CALDERA_EVIDENCE_PATH, CALDERA_REFERENCE_MANIFEST_PATH),
        ("caldera-c0010", caldera_c0010_archive, caldera_c0010_reference,
         Path("typed-run-evidence/caldera-c0010.tar.gz"),
         Path("typed-run-evidence/caldera-c0010-reference-run-source-tree.json")),
    ):
        if (supplied_archive is None) != (supplied_reference is None):
            raise ValueError("The CALDERA archive and its reference manifest go together")
        if supplied_archive is None:
            continue
        caldera_source = supplied_archive.resolve(strict=True)
        caldera_reference = supplied_reference.resolve(strict=True)
        if caldera_source.is_relative_to(destination.resolve()):
            raise ValueError("CALDERA evidence archive must be outside the destination")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(STICKS_ROOT / "src"), str(STICKS_ROOT), environment.get("PYTHONPATH", ""))
        )
        for module, *extra in (
            ("scripts.verify_typed_evidence_archive",),
            ("scripts.screen_typed_evidence_privacy",
             "--bound-reference-manifest", str(caldera_reference)),
        ):
            subprocess.run(
                [sys.executable, "-m", module, "--archive", str(caldera_source),
                 "--series", series, *extra],
                cwd=STICKS_ROOT, check=True, env=environment,
            )
        caldera_sources.append((caldera_source, caldera_reference, target_archive, target_reference))
    if c0045_series_archive is not None:
        source_series = c0045_series_archive.resolve(strict=True)
        if source_series.is_relative_to(destination.resolve()):
            raise ValueError("C0045 series archive must be outside the destination")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(STICKS_ROOT / "src"), str(STICKS_ROOT), environment.get("PYTHONPATH", ""))
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.verify_c0045_effect_series_archive",
                "--archive",
                str(source_series),
            ],
            cwd=STICKS_ROOT,
            check=True,
            env=environment,
        )
        if c0045_privacy_review is not None:
            review_source = c0045_privacy_review.resolve(strict=True)
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.verify_c0045_series_privacy_review",
                    "--archive",
                    str(source_series),
                    "--review",
                    str(review_source),
                ],
                cwd=STICKS_ROOT,
                check=True,
                env=environment,
            )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.screen_c0045_series_privacy",
                "--archive",
                str(source_series),
            ],
            cwd=STICKS_ROOT,
            check=True,
            env=environment,
        )
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    stage_root(destination)
    write_repo_docs(
        destination,
        repository_url,
        bundled_typed_evidence=typed_evidence_archive is not None,
        bundled_typed_reference=typed_evidence_reference_manifest is not None,
        bundled_bound_typed_reference=typed_evidence_bound_reference_manifest is not None,
        bundled_c0045_series=c0045_series_archive is not None,
        public_evidence_release=public_evidence_release or identified_release,
        anonymous_review=anonymous_review,
    )
    if typed_evidence_archive is not None:
        target = destination / TYPED_EVIDENCE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if reference_manifest is not None:
            target_reference = (
                TYPED_BOUND_REFERENCE_MANIFEST_PATH
                if typed_evidence_bound_reference_manifest is not None
                else TYPED_REFERENCE_MANIFEST_PATH
            )
            shutil.copyfile(reference_source, destination / target_reference)
    for caldera_source, caldera_reference, target_archive, target_reference in caldera_sources:
        target = destination / target_archive
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(caldera_source, target)
        shutil.copyfile(caldera_reference, destination / target_reference)
    if c0045_series_archive is not None:
        target = destination / C0045_SERIES_ARCHIVE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_series, target)
        if c0045_privacy_review is not None:
            review_target = destination / "release/privacy/c0045-series-review.json"
            review_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(c0045_privacy_review, review_target)
    rendering_environment = os.environ.copy()
    rendering_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for renderer in (
        "render_provenance_table.py",
        "render_enrichment_baseline_table.py",
        "render_execution_commitments_table.py",
        "render_claim_ledger_table.py",
        "render_admission_comparison_table.py",
        "build_fidelity_rationale.py",
    ):
        subprocess.run(
            [sys.executable, f"scripts/{renderer}"],
            cwd=destination,
            check=True,
            env=rendering_environment,
        )
    subprocess.run(
        [
            sys.executable,
            "scripts/public_tree_manifest.py",
            "write",
            "--root",
            str(destination),
        ],
        cwd=destination,
        check=True,
    )


def require_clean_release_artifacts(destination: Path) -> None:
    artifacts_root = destination / "data" / "artifacts"
    residual_files = sorted(
        str(path.relative_to(destination))
        for path in artifacts_root.rglob("*")
        if path.is_file() or path.is_symlink()
    )
    if residual_files:
        raise RuntimeError(f"release validation left runtime artifacts: {residual_files}")


def validate_stage(destination: Path) -> None:
    require_clean_release_artifacts(destination)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(
        ["bash", "run_review_check.sh"],
        cwd=destination,
        env=environment,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/public_tree_manifest.py",
            "verify",
            "--root",
            str(destination),
        ],
        cwd=destination,
        env=environment,
        check=True,
    )
    require_clean_release_artifacts(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        default=str(DEFAULT_DEST),
        help="destination directory for the staged repository",
    )
    parser.add_argument(
        "--repository-url",
        help="optional final public URL to record in the staged manifest",
    )
    parser.add_argument(
        "--typed-evidence-archive",
        type=Path,
        help="validated QEMU evidence archive to bundle in the candidate",
    )
    parser.add_argument(
        "--typed-evidence-reference-manifest",
        type=Path,
        help="exact known-public manifest for the bundled historical typed archive",
    )
    parser.add_argument(
        "--typed-evidence-bound-reference-manifest",
        type=Path,
        help="manifest byte-identical to both sealed run source workspaces",
    )
    parser.add_argument(
        "--caldera-evidence-archive",
        type=Path,
        help="screened typed archive of the C0026 cycle dispatched through CALDERA",
    )
    parser.add_argument(
        "--caldera-reference-manifest",
        type=Path,
        help="manifest byte-identical to the CALDERA run's sealed source workspace",
    )
    parser.add_argument("--caldera-c0010-archive", type=Path,
                        help="screened operational C0010 CALDERA archive")
    parser.add_argument("--caldera-c0010-reference", type=Path,
                        help="manifest bound to the sealed C0010 source workspace")
    parser.add_argument(
        "--c0045-series-archive",
        type=Path,
        help="validated private C0045 compute-effect series archive to bundle",
    )
    parser.add_argument(
        "--c0045-privacy-review",
        type=Path,
        help="hash-bound semantic review required to bundle C0045 in a candidate",
    )
    parser.add_argument(
        "--public-evidence-release",
        action="store_true",
        help="use public release wording after separate content and privacy review",
    )
    parser.add_argument(
        "--anonymous-review",
        action="store_true",
        help="refuse a repository URL in this review candidate; separate privacy review is required",
    )
    parser.add_argument(
        "--identified-release",
        action="store_true",
        help="explicitly permit an identifying repository URL in a non-anonymous release",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="stage files without running the public-surface gate",
    )
    args = parser.parse_args()

    if args.repository_url and "REPLACE" in args.repository_url.upper():
        raise SystemExit("repository URL contains an unresolved placeholder")
    if args.anonymous_review and args.repository_url:
        parser.error("--anonymous-review cannot be combined with --repository-url")
    if args.anonymous_review and args.identified_release:
        parser.error("--anonymous-review cannot be combined with --identified-release")
    if args.repository_url and not args.identified_release:
        parser.error("--repository-url requires --identified-release")
    if args.identified_release and not args.repository_url:
        parser.error("--identified-release requires --repository-url")

    destination = Path(args.dest).resolve()
    stage(
        destination,
        args.repository_url,
        typed_evidence_archive=args.typed_evidence_archive,
        typed_evidence_reference_manifest=args.typed_evidence_reference_manifest,
        typed_evidence_bound_reference_manifest=args.typed_evidence_bound_reference_manifest,
        c0045_series_archive=args.c0045_series_archive,
        c0045_privacy_review=args.c0045_privacy_review,
        caldera_evidence_archive=args.caldera_evidence_archive,
        caldera_reference_manifest=args.caldera_reference_manifest,
        caldera_c0010_archive=args.caldera_c0010_archive,
        caldera_c0010_reference=args.caldera_c0010_reference,
        public_evidence_release=args.public_evidence_release,
        anonymous_review=args.anonymous_review,
        identified_release=args.identified_release,
    )
    if not args.skip_validation:
        validate_stage(destination)
    if args.anonymous_review:
        label = "anonymous reviewer candidate"
    elif args.public_evidence_release:
        label = "public evidence candidate"
    elif args.typed_evidence_archive:
        label = "private evidence candidate"
    else:
        label = "public repository candidate"
    print(f"[OK] Staged {label} at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
