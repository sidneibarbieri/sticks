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
PAPER_AUTHORING_RUNS = tuple(json.loads(
    (STICKS_ROOT / "release" / "experiments" / "stage2_authoring" / "paper_runs.json").read_text(encoding="utf-8")
)["run_ids"])
PUBLIC_COMPARISON_ENTRIES = frozenset({
    "2026-09-07-local",
    "2026-09-07-qwen14b",
    "qualification_status.json",
})
DEFAULT_DEST = STICKS_ROOT.parent / "release-staging" / "sticks-artifact"
TYPED_EVIDENCE_PATH = Path("typed-run-evidence/c0010-c0026.tar.gz")
TYPED_REFERENCE_MANIFEST_PATH = Path(
    "typed-run-evidence/reference-public-tree-4c52b4e.json"
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
    "docs/COVERAGE_EVIDENCE_SELECTION.md",
]

ROOT_DIRS = [
    "artifact",
    "campaigns",
    "data",
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

    write_text(
        destination / "README.md",
        """
        # STICKS Public Artifact

        STICKS is a finite-domain procedural-admission artifact. It compiles pinned
        ATT&CK campaign structure into typed plans, enumerates candidates from a
        versioned template catalog, checks them against an explicitly scoped state,
        and records what the CTI, environment, and reconstruction each contribute.

        ## Repository structure

        - `src/`: compiler, contracts, finite-domain concretization, and evaluation.
        - `data/`: pinned STIX input and versioned procedure-template catalog.
        - `release/`: plans, experiment records, claim ledger, and evidence hashes.
        - `docs/`: reconstruction, realization-space, and state-fact semantics.
        - `tests/`: executable checks linked from the claim ledger.

        ## Evaluation qualities

        This release is prepared for availability, functionality, sustainability,
        and experiment-reproducibility review. Availability also depends on the
        distribution channel providing this package through a stable public URL.

        ## Basic information

        The primary path requires a POSIX-like shell, Python 3.11 or later, `venv`,
        and `pip`. The reference dependency lock targets Python 3.11.15. No GPU is
        needed. A machine with two CPU cores, 4 GiB of RAM, and 1 GiB of free disk is
        sufficient for the primary gate; allow five minutes after dependencies are
        installed. Runtime varies by host.

        ## Dependencies

        `requirements.lock` records every direct and transitive Python dependency at
        an exact version. `requirements.txt` installs that lock without resolving an
        unpinned package set. The pinned ATT&CK input and template catalog ship in the
        repository, so the experiment path does not fetch data at runtime.

        ## Security considerations

        The primary reviewer path performs deterministic local computation and one
        benign loopback transfer. It requires no credentials, external service,
        container runtime, hypervisor, or model API. The secondary legacy path can
        manage virtual machines and adversary-emulation infrastructure; run it only
        in an isolated disposable laboratory. It is not needed for registered claims.

        ## Installation

        ```bash
        python3 -m venv .venv
        .venv/bin/python -m pip install -r requirements.txt
        ```

        ## Minimal test

        ```bash
        .venv/bin/python -m pytest tests/test_realization_space.py -q -p no:cacheprovider
        ```

        Expected result: every realization-space test passes and the process exits
        with status zero.

        ## Optional QA dependencies

        The primary lock does not include the legacy HTTP client. To exercise the
        mocked legacy infrastructure paths, create a separate QA environment:

        ```bash
        python3 -m venv .venv-qa
        .venv-qa/bin/python -m pip install -r requirements-qa.txt
        .venv-qa/bin/python -m pip check
        .venv-qa/bin/python -m pytest tests/test_legacy_infrastructure_paths.py -q -p no:cacheprovider
        ```

        This exact optional Python profile extends, rather than replaces, the
        primary lock. These tests mock provider calls: passing is not VM campaign
        qualification. Installation needs package-index access; the tests do not.

        `tests/test_qemu_network_serialization.py` requires Ruby with its YAML
        standard library. `tests/test_workbench_browser_state.py` requires Node.js
        on PATH for its JavaScript state test. Without those interpreters the
        corresponding tests explicitly skip. To check them when available:

        ```bash
        ruby -ryaml -e 'puts RUBY_VERSION'
        node --version
        .venv-qa/bin/python -m pytest tests/test_qemu_network_serialization.py tests/test_workbench_browser_state.py -q -p no:cacheprovider
        ```

        These checks do not boot a VM or measure campaign effects. Tests requiring
        real lab-run evidence can still skip when that evidence is absent. Report
        executed and skipped tests separately; installing QA dependencies does
        not supply missing execution evidence.

        To select an existing environment for the complete reviewer wrapper:

        ```bash
        STICKS_PYTHON="$PWD/.venv-qa/bin/python" bash run_review_check.sh
        ```

        `STICKS_PYTHON` overrides the repository `.venv` and PATH. It must name an
        executable interpreter with core dependencies. An invalid selection fails
        without installation or fallback. Without it, the wrapper retains the
        repository `.venv`, then PATH selection. Install the chosen profile before
        running the wrapper; this selector does not verify exact dependency pins.

        ## Experiments

        ### Inspect admission in the graphical workbench

        ```bash
        .venv/bin/python scripts/run_realization_workbench.py --host 127.0.0.1 --port 8765
        ```

        Open `http://127.0.0.1:8765/` to inspect the pinned campaign inventory and
        bounded candidate admission. This is a planning interface, not campaign
        execution evidence. Stop the server with Ctrl-C. See
        `docs/reviewer_quickstart.md` for scope and the canonical validation path.

        ### Reproduce the registered evidence

        The following command reproduces every non-blocked registered property:

        ```bash
        bash run_review_check.sh
        ```

        After dependency installation, this command is offline. It regenerates the
        evidence, validates SHA-256 hashes, audits claim chains, checks the public
        surface and complete public-tree manifest, and runs the tests. It needs no
        Docker, VM, API key, or paid model.

        Expected headline output includes {{corpusCampaignCount}} campaigns and
        {{corpusStepCount}} steps in the corpus, {{corpusSupportedSteps}} catalog-supported
        steps, {{rawAdmittedSteps}}/{{deepStepCount}} admitted steps from the unaugmented
        representation versus {{enrichedAdmittedSteps}}/{{deepStepCount}} reconstructed steps
        in the deep slice, {{bindingOccurrences}} binding occurrences, and
        {{totalCommitments}} explicit execution commitments.

        ### Corpus coverage and deep admission

        `bash run_review_check.sh` recompiles all released Enterprise campaigns and
        regenerates the corpus-coverage and three-campaign deep-slice records. Inspect
        `release/experiments/` and `release/claims/verification.json`. Expected result:
        all non-blocked ledger properties verify; limited and blocked properties remain
        visibly qualified rather than being promoted.

        ### Bounded realization-space example

        ```bash
        .venv/bin/python scripts/enumerate_realization_space.py \
          --plan release/plans/C0010.procedural-plan.json \
          --bindings release/plans/C0010.binding-catalog.json \
          --templates data/concretization/action_templates.json \
          --maximum-realizations 64 \
          --maximum-search-states 20000 \
          --output /tmp/C0010.realization-space.json \
          --require-realization
        ```

        Expected result: a bounded, hash-valid space with 64 serialized schedule
        graphs, one causal structure, and operational status `not_run`. This command
        enumerates candidates; it does not claim that they were executed.

        ### State-fact semantic audit

        ```bash
        .venv/bin/python scripts/audit_fact_semantics.py \
          --output /tmp/fact-semantics-audit.json
        ```

        Expected result: all three frozen deep-slice SUT catalogs are conformant.
        The check verifies versioned fact identity and permitted origins only; it
        does not establish a live state or operational effect. See
        `docs/FACT_SEMANTICS.md` for the contract and non-claims.

        ## Evidence map

        - `release/claims/ledger.json`: registered and blocked properties.
        - `release/claims/evidence_sha256.json`: frozen integrity manifest.
        - `release/experiments/`: generated experiment records and tables.
        - `release/plans/`: typed plans, catalogs, and concretized plans.
        - `release/paper_macros.tex`: generated manuscript values.
        - `PUBLIC_TREE_SHA256.json`: hash and size of every shipped file.
        - `tests/`: checks linked from the ledger.

        When a manuscript source is colocated with the artifact, audit it too:

        ```bash
        PAPER_DIR=../paper bash run_review_check.sh
        ```

        ## Interpretation boundary

        The catalog supports {{corpusSupportedSteps}} of {{corpusStepCount}} corpus steps
        ({{corpusCoveragePct}}%). The deep evaluation
        covers three fully supported campaigns and demonstrates the admission
        mechanism, not corpus-wide replay coverage. The artifact does not claim
        historical reconstruction, full campaign replay, observational equivalence,
        or analyst-effort reduction.

        ## Secondary legacy experiments

        Earlier container, VM, and SUT experiments remain available for inspection and
        compatibility. They are outside the primary claim ledger:

        ```bash
        bash run_review_check.sh --legacy
        ```

        A green legacy check does not support a property absent from the ledger.
        For a new VM-backed campaign with isolated source, raw artifacts, and
        evidence, use `scripts/run_isolated_lab_campaign.py`. Platform setup,
        the pinned Node cache option, and interpretation limits are in
        `docs/IAC_LIMITATIONS_ARM64.md`. This path requires a hypervisor and
        network access, unlike the offline primary gate.

        For a retained QEMU Linux run, `scripts/observe_controlled_target.py`
        checks declared fixtures, a benign loopback transfer, and the preserved
        browser-discovery report without importing the executors. The command,
        explicit scope, failure behavior, and teardown requirement are documented
        in `docs/IAC_LIMITATIONS_ARM64.md`. This does not qualify unrelated
        techniques or historical fidelity.

        The C0026 target-chain profile has a separate completion command:
        `scripts/complete_c0026_run.py --run-root PATH`. It uploads and runs
        the packaged target probe, attempts campaign-scoped teardown even when
        observation fails, and seals the final receipt only after success.
        See `lab/vagrant/README.md` for the complete command sequence.

        ### Prospective C0026 dispatch through CALDERA

        This optional path enrolls a fresh Linux target agent, binds dispatch to
        its boot identity, and retains command intents, native links, and results.
        Independent effect probes use a separate transport.

        ```bash
        python scripts/run_isolated_lab_campaign.py --campaign 0.c0026 --provider qemu --run-root /absolute/new/run --caldera-dispatch --keep-lab
        python scripts/complete_c0026_run.py --run-root /absolute/new/run
        python scripts/finalize_isolated_lab_run.py --run-root /absolute/new/run --verify
        python scripts/verify_caldera_run_journal.py --evidence /absolute/new/run/evidence
        ```

        Completion observes the target, tears down the guests, and seals the
        receipt. Run completion even after a failed campaign; failure propagates
        and an invalid journal prevents certification. This controlled C0026
        slice includes an explicit simulation. It does not demonstrate an
        enterprise multi-host pivot. Offline review does not execute this path.

        For two sealed QEMU runs created from the same source tree, retain both
        run directories and audit their typed outcomes with:

        ```bash
        PYTHONPATH=src:. python3 -m scripts.audit_typed_campaign_outcomes \\
          --run-root /path/to/C0010-run --run-root /path/to/C0026-run
        ```

        The auditor recomputes each final receipt and reports observed effects
        on the target and controller separately from simulations and failures.
        It checks the recorded VM teardown states against the required VM names
        without invoking Vagrant; it cannot re-observe the historical teardown.
        It rejects different source trees. The default offline package contains no
        QEMU run directories; this command validates new or separately
        supplied runs. Passing the offline review check alone does not
        establish VM-backed campaign execution.

        If a separately supplied typed-evidence archive accompanies this
        repository, verify it from the package root with:

        ```bash
        PYTHONPATH=src:. python3 -m scripts.verify_typed_evidence_archive \\
          --archive /path/to/typed-qemu-evidence.tar.gz
        ```

        This command rejects archive links, unsafe paths, AppleDouble files,
        and oversized members before extracting into a temporary directory.
        It then verifies both sealed receipts using their recorded VM states.
        When `--typed-evidence-archive` is supplied, the package includes
        `typed-run-evidence/c0010-c0026.tar.gz`, binds its bytes in
        `PUBLIC_TREE_SHA256.json`, and verifies it during `run_review_check.sh`.
        This checks recorded outcomes, not a new VM execution or publication safety.
        No QEMU result should be inferred when the archive is absent.

        ## License

        STICKS-authored material is released under the MIT License; see
        `LICENSE`. Pinned third-party inputs have separate terms recorded in
        `THIRD_PARTY_NOTICES.md`.
        """,
    )

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
        raise ValueError("C0045 series is approved only for anonymous review")
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
        public_evidence_release=public_evidence_release,
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
