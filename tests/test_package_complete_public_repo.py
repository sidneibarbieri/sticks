from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / "scripts" / "package_complete_public_repo.py"


def test_pinned_third_party_inputs_have_notice_in_package(tmp_path: Path) -> None:
    module = _load_module()
    module.stage_root(tmp_path)
    notice = (tmp_path / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "data/stix/enterprise-attack.json" in notice
    assert "© 2026 The MITRE Corporation" in notice
    assert "data/interop/equifax-breach.afb" in notice
    assert "measurement/sut/scripts/data/stix-capec.json" in notice
    attack_flow_license = (
        tmp_path / "THIRD_PARTY_LICENSES/ATTACK_FLOW_APACHE-2.0.txt"
    ).read_text(encoding="utf-8")
    assert "Apache License" in attack_flow_license
    assert "Version 2.0, January 2004" in attack_flow_license
    mitre_cti_license = (
        tmp_path / "THIRD_PARTY_LICENSES/MITRE_CTI_LICENSE.txt"
    ).read_text(encoding="utf-8")
    assert "CAPEC" in mitre_cti_license
    assert "MITRE" in mitre_cti_license
    example = tmp_path / "examples/atomic_hostname"
    assert (example / "qualify.py").is_file()
    assert (example / "qualified/qualification.json").is_file()
    assert "Red Canary" in (example / "LICENSE.upstream.txt").read_text()


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "sticks_package_complete_public_repo", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _typed_evidence_inputs(tmp_path: Path) -> dict[str, Path]:
    archive = tmp_path / "evidence.tar.gz"
    archive.write_bytes(b"archive")
    reference = tmp_path / "bound-reference.json"
    reference.write_bytes(b"manifest")
    return {
        "typed_evidence_archive": archive,
        "typed_evidence_bound_reference_manifest": reference,
    }


def test_release_validation_rejects_runtime_artifacts_created_by_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    artifacts_root = tmp_path / "data" / "artifacts"
    calls = []

    def run_review(command, **kwargs):
        calls.append(command)
        if command[:2] == ["bash", "run_review_check.sh"]:
            artifacts_root.mkdir(parents=True)
            (artifacts_root / "domain_registration.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(module.subprocess, "run", run_review)

    with pytest.raises(RuntimeError, match="domain_registration.json"):
        module.validate_stage(tmp_path)

    assert len(calls) == 2


def test_release_validation_rejects_preexisting_runtime_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    artifacts_root = tmp_path / "data" / "artifacts"
    artifacts_root.mkdir(parents=True)
    (artifacts_root / "leftover.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        module.subprocess, "run", lambda *args, **kwargs: pytest.fail("review should not run")
    )

    with pytest.raises(RuntimeError, match="leftover.json"):
        module.validate_stage(tmp_path)


def test_stage_refreshes_derived_tables_before_freezing_manifest(tmp_path, monkeypatch):
    module = _load_module()
    calls = []
    monkeypatch.setattr(module, "stage_root", lambda destination: calls.append("copy"))
    monkeypatch.setattr(
        module, "write_repo_docs", lambda destination, repository_url, **kwargs: calls.append("docs")
    )

    def record_run(command, *, cwd, check, **kwargs):
        assert cwd == tmp_path / "candidate"
        assert check is True
        if command[1].startswith("scripts/render_"):
            assert kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
        calls.append(command[1])

    monkeypatch.setattr(module.subprocess, "run", record_run)
    module.stage(tmp_path / "candidate")

    assert calls == [
        "copy", "docs", "scripts/render_provenance_table.py",
        "scripts/render_enrichment_baseline_table.py",
        "scripts/render_execution_commitments_table.py",
        "scripts/render_claim_ledger_table.py",
        "scripts/render_admission_comparison_table.py",
        "scripts/build_fidelity_rationale.py", "scripts/public_tree_manifest.py",
    ]


def test_anonymous_stage_rejects_identifying_repository_url_before_replacing_destination(
    tmp_path: Path,
) -> None:
    module = _load_module()
    destination = tmp_path / "candidate"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("preserve existing candidate\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Anonymous review candidates cannot record a repository URL"):
        module.stage(
            destination,
            repository_url="https://github.com/example/sticks-artifact",
            anonymous_review=True,
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve existing candidate\n"


def test_stage_rejects_repository_url_without_identified_release(
    tmp_path: Path,
) -> None:
    module = _load_module()
    destination = tmp_path / "candidate"

    with pytest.raises(ValueError, match="requires identified_release=True"):
        module.stage(
            destination,
            repository_url="https://github.com/example/sticks-artifact",
        )

    assert not destination.exists()


def test_stage_identified_release_accepts_repository_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    destination = tmp_path / "candidate"
    received_urls = []
    received_public_modes = []
    monkeypatch.setattr(module, "stage_root", lambda target: None)
    monkeypatch.setattr(
        module,
        "write_repo_docs",
        lambda target, repository_url, **kwargs: (
            received_urls.append(repository_url),
            received_public_modes.append(kwargs["public_evidence_release"]),
        ),
    )
    monkeypatch.setattr(module.subprocess, "run", lambda command, *, cwd, check, **kwargs: None)

    module.stage(
        destination,
        repository_url="https://github.com/example/sticks-artifact",
        identified_release=True,
        **_typed_evidence_inputs(tmp_path),
    )
    assert received_public_modes == [True]

    assert received_urls == ["https://github.com/example/sticks-artifact"]


def test_anonymous_stage_without_repository_url_reaches_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    destination = tmp_path / "candidate"
    monkeypatch.setattr(module, "stage_root", lambda target: None)
    monkeypatch.setattr(module, "write_repo_docs", lambda target, repository_url, **kwargs: None)
    monkeypatch.setattr(module.subprocess, "run", lambda command, *, cwd, check, **kwargs: None)

    module.stage(destination, anonymous_review=True, **_typed_evidence_inputs(tmp_path))

    assert destination.is_dir()


def test_anonymous_cli_rejects_repository_url_before_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    destination = tmp_path / "candidate"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(MODULE_PATH),
            "--dest",
            str(destination),
            "--anonymous-review",
            "--repository-url",
            "https://github.com/example/sticks-artifact",
        ],
    )

    with pytest.raises(SystemExit) as error:
        module.main()

    assert error.value.code == 2
    assert not destination.exists()


def test_cli_rejects_repository_url_without_identified_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    destination = tmp_path / "candidate"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(MODULE_PATH),
            "--dest",
            str(destination),
            "--public-evidence-release",
            "--typed-evidence-archive",
            str(tmp_path / "sealed-evidence.tar.gz"),
            "--repository-url",
            "https://github.com/example/sticks-artifact",
        ],
    )

    with pytest.raises(SystemExit) as error:
        module.main()

    assert error.value.code == 2
    assert not destination.exists()


def test_stage_stops_before_manifest_if_table_rendering_fails(tmp_path, monkeypatch):
    module = _load_module()
    calls = []
    monkeypatch.setattr(module, "stage_root", lambda destination: None)
    monkeypatch.setattr(module, "write_repo_docs", lambda destination, repository_url, **kwargs: None)

    def fail_render(command, *, cwd, check, **kwargs):
        calls.append(command[1])
        raise module.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(module.subprocess, "run", fail_render)
    with pytest.raises(module.subprocess.CalledProcessError):
        module.stage(tmp_path / "candidate")
    assert calls == ["scripts/render_provenance_table.py"]


def test_stage_preserves_coverage_evidence_instructions(tmp_path, monkeypatch):
    module = _load_module()
    source_root = tmp_path / "source"
    instructions = source_root / "docs/COVERAGE_EVIDENCE_SELECTION.md"
    instructions.parent.mkdir(parents=True)
    instructions.write_text("Use explicit prospective evidence inputs.\n")
    monkeypatch.setattr(module, "STICKS_ROOT", source_root)
    destination = tmp_path / "candidate"
    module.stage_root(destination)
    assert (destination / "docs/COVERAGE_EVIDENCE_SELECTION.md").read_bytes() == instructions.read_bytes()


def test_measurement_sut_internal_docs_are_excluded_from_public_package() -> None:
    module = _load_module()
    ignore = module.ignore_for_directory("measurement")
    sut_dir = module.STICKS_ROOT / "measurement" / "sut"
    names = [
        "FINAL_STATUS.md",
        "PUBLICATION_CHECKLIST.md",
        "README.md",
        "TRACEABILITY.md",
    ]

    ignored = ignore(str(sut_dir), names)

    assert "FINAL_STATUS.md" in ignored
    assert "PUBLICATION_CHECKLIST.md" in ignored
    assert "README.md" not in ignored
    assert "TRACEABILITY.md" not in ignored


def test_generated_artifacts_and_nested_vagrant_state_are_excluded() -> None:
    module = _load_module()
    data_ignore = module.ignore_for_directory("data")
    data_dir = module.STICKS_ROOT / "data"
    assert "artifacts" in data_ignore(str(data_dir), ["artifacts", "stix"])

    lab_ignore = module.ignore_for_directory("lab")
    nested_lab_dir = module.STICKS_ROOT / "lab" / "vagrant" / "target-linux-1"
    ignored = lab_ignore(str(nested_lab_dir), [".vagrant", "Vagrantfile"])
    assert ".vagrant" in ignored
    assert "Vagrantfile" not in ignored


def test_public_copy_omits_gitignored_build_metadata_and_host_timing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    source = tmp_path / "source"
    (source / "src/sticks.egg-info").mkdir(parents=True)
    (source / "src/sticks.egg-info/PKG-INFO").write_text("generated")
    (source / "src/sticks/__init__.py").parent.mkdir()
    (source / "src/sticks/__init__.py").write_text("", encoding="utf-8")
    timing = source / "release/experiments/enumeration_scaling/timing.json"
    timing.parent.mkdir(parents=True)
    timing.write_text("{}", encoding="utf-8")
    (timing.parent / "corpus.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(module, "STICKS_ROOT", source)

    module.copy_tree(source / "src", tmp_path / "output/src", "src")
    module.copy_tree(source / "release", tmp_path / "output/release", "release")

    assert (tmp_path / "output/src/sticks/__init__.py").is_file()
    assert (tmp_path / "output/release/experiments/enumeration_scaling/corpus.json").is_file()
    assert not (tmp_path / "output/src/sticks.egg-info").exists()
    assert not (tmp_path / "output/release/experiments/enumeration_scaling/timing.json").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_runtime_reports_are_ignored_by_release_git(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_bytes((PROJECT_ROOT / ".gitignore").read_bytes())
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    for path in (
        "results/enumeration_scaling_timing.json",
        "results/PUBLIC_SURFACE_REPORT.md",
        "results/public_surface_report.json",
    ):
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", path], cwd=tmp_path, check=False
        )
        assert result.returncode == 0, path


def test_only_canonical_release_roots_enter_public_package() -> None:
    module = _load_module()
    release_ignore = module.ignore_for_directory("release")
    release_dir = module.STICKS_ROOT / "release"
    names = [
        "claims",
        "experiments",
        "plans",
        "paper_macros.tex",
        "linux_discovery_macros.tex",
        "CLAIMS_EVIDENCE_MATRIX.md",
        "PAPER_READY_SUMMARY.md",
        "performance_metrics.tex",
    ]

    ignored = release_ignore(str(release_dir), names)

    assert {"claims", "experiments", "plans", "paper_macros.tex",
            "linux_discovery_macros.tex"}.isdisjoint(
        ignored
    )
    assert {
        "CLAIMS_EVIDENCE_MATRIX.md",
        "PAPER_READY_SUMMARY.md",
        "performance_metrics.tex",
    }.issubset(ignored)


def test_only_paper_cited_authoring_runs_enter_the_public_package() -> None:
    module = _load_module()
    release_ignore = module.ignore_for_directory("release")
    authoring_dir = module.STICKS_ROOT / "release" / "experiments" / "stage2_authoring"
    names = ["calls", "corpus.json", "generation_summary.json", "runs"]

    ignored = release_ignore(str(authoring_dir), names)

    assert ignored == set()
    run_names = [*module.PAPER_AUTHORING_RUNS, "unreviewed-run"]
    assert release_ignore(str(authoring_dir / "runs"), run_names) == {"unreviewed-run"}


def test_unreviewed_comparison_runs_do_not_enter_public_package() -> None:
    module = _load_module()
    release_ignore = module.ignore_for_directory("release")
    comparison_dir = module.STICKS_ROOT / "release/experiments/controlled_comparison"
    run_names = [*module.PUBLIC_COMPARISON_ENTRIES, "prospective-qwen36-20261019"]

    assert release_ignore(str(comparison_dir), run_names) == {
        "prospective-qwen36-20261019"
    }
    assert "qualification_status.json" in module.PUBLIC_COMPARISON_ENTRIES
    assert (comparison_dir / "qualification_status.json").is_file()


def test_stage_rejects_missing_qualification_status_before_replacing_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "STICKS_ROOT", tmp_path / "source")
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    sentinel = candidate / "keep.txt"
    sentinel.write_text("preserve candidate\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="qualification_status.json"):
        module.stage(candidate)

    assert sentinel.read_text(encoding="utf-8") == "preserve candidate\n"


def test_preexisting_results_are_never_staged() -> None:
    module = _load_module()
    results_ignore = module.ignore_for_directory("results")
    results_dir = module.STICKS_ROOT / "results"
    names = ["CLAIMS_FOR_PAPER.md", "fidelity_report.json", "tables"]

    assert results_ignore(str(results_dir), names) == set(names)


def test_manuscript_build_products_are_banned_from_public_review_package() -> None:
    module = _load_module()
    public_surface_path = module.STICKS_ROOT / "scripts" / "check_public_surface.py"
    public_surface = public_surface_path.read_text(encoding="utf-8")
    assert '"paper/build_artifacts/main.pdf"' in public_surface


def test_generated_reviewer_docs_use_the_primary_ledger_path(tmp_path: Path) -> None:
    module = _load_module()
    module.write_repo_docs(tmp_path, repository_url=None)

    wrapper = (tmp_path / "run_review_check.sh").read_text(encoding="utf-8")
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    manifest = (tmp_path / "ARTIFACT_MANIFEST.md").read_text(encoding="utf-8")

    assert "scripts/reproduce.py" in wrapper
    assert "release/claims/ledger.json" in readme
    assert "scripts/audit_fact_semantics.py" in readme
    assert "docs/FACT_SEMANTICS.md" in readme
    assert "docs/IAC_LIMITATIONS_ARM64.md" in readme
    assert "scripts/run_isolated_lab_campaign.py" in readme
    assert "scripts/complete_c0026_run.py" in readme
    assert "scripts.audit_typed_campaign_outcomes" in readme
    assert "scripts.verify_typed_evidence_archive" in readme
    assert "--archive /path/to/typed-qemu-evidence.tar.gz" in readme
    assert "default offline package contains no" in readme
    assert "--legacy" in readme
    assert "REPLACE-WITH" not in manifest


def test_private_candidate_verifies_before_replacing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    archive = tmp_path / "evidence.tar.gz"
    archive.write_bytes(b"invalid archive")
    destination = tmp_path / "candidate"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("preserved")

    def fail_validation(command, *, cwd, check, env):
        assert command[2] == "scripts.verify_typed_evidence_archive"
        assert cwd == module.STICKS_ROOT
        assert check is True
        assert str(module.STICKS_ROOT / "src") in env["PYTHONPATH"]
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(module.subprocess, "run", fail_validation)
    with pytest.raises(subprocess.CalledProcessError):
        module.stage(destination, typed_evidence_archive=archive)
    assert marker.read_text() == "preserved"


def test_c0045_series_verifies_before_replacing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    archive = tmp_path / "series.tar.gz"
    archive.write_bytes(b"invalid archive")
    destination = tmp_path / "candidate"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("preserved")

    def fail_validation(command, *, cwd, check, env):
        assert command[2] == "scripts.verify_c0045_effect_series_archive"
        assert cwd == module.STICKS_ROOT
        assert check is True
        assert str(module.STICKS_ROOT / "src") in env["PYTHONPATH"]
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(module.subprocess, "run", fail_validation)
    with pytest.raises(subprocess.CalledProcessError):
        module.stage(destination, c0045_series_archive=archive)
    assert marker.read_text() == "preserved"


def test_c0045_privacy_screen_blocks_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    archive = tmp_path / "series.tar.gz"
    archive.write_bytes(b"archive")
    destination = tmp_path / "candidate"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("preserved", encoding="utf-8")
    calls: list[str] = []

    def fail_screen(command, *, cwd, check, env):
        calls.append(command[2])
        assert cwd == module.STICKS_ROOT
        assert check is True
        if command[2] == "scripts.screen_c0045_series_privacy":
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(module.subprocess, "run", fail_screen)
    with pytest.raises(subprocess.CalledProcessError):
        module.stage(destination, c0045_series_archive=archive)

    assert calls == [
        "scripts.verify_c0045_effect_series_archive",
        "scripts.screen_c0045_series_privacy",
    ]
    assert marker.read_text(encoding="utf-8") == "preserved"


def test_typed_reference_verifies_before_replacing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    archive = tmp_path / "evidence.tar.gz"
    archive.write_bytes(b"archive")
    reference = tmp_path / "reference.json"
    reference.write_bytes(b"manifest")
    destination = tmp_path / "candidate"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("preserved")
    calls = []

    def fail_screen(command, *, cwd, check, env):
        calls.append(command[2])
        if command[2] == "scripts.screen_typed_evidence_privacy":
            assert command[-2:] == ["--known-reference-manifest", str(reference)]
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(module.subprocess, "run", fail_screen)
    with pytest.raises(subprocess.CalledProcessError):
        module.stage(
            destination,
            typed_evidence_archive=archive,
            typed_evidence_reference_manifest=reference,
        )
    assert calls == [
        "scripts.verify_typed_evidence_archive",
        "scripts.screen_typed_evidence_privacy",
    ]
    assert marker.read_text() == "preserved"


def test_typed_reference_is_copied_before_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    archive = tmp_path / "evidence.tar.gz"
    archive.write_bytes(b"archive")
    reference = tmp_path / "reference.json"
    reference.write_bytes(b"manifest")
    destination = tmp_path / "candidate"
    monkeypatch.setattr(module, "stage_root", lambda target: None)
    monkeypatch.setattr(module, "write_repo_docs", lambda *args, **kwargs: None)

    def record_run(command, *, cwd, check, **kwargs):
        if "scripts/public_tree_manifest.py" in command:
            assert (destination / module.TYPED_EVIDENCE_PATH).read_bytes() == b"archive"
            assert (destination / module.TYPED_REFERENCE_MANIFEST_PATH).read_bytes() == b"manifest"

    monkeypatch.setattr(module.subprocess, "run", record_run)
    module.stage(
        destination,
        typed_evidence_archive=archive,
        typed_evidence_reference_manifest=reference,
    )


def test_bound_typed_reference_is_checked_and_copied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    archive = tmp_path / "evidence.tar.gz"
    archive.write_bytes(b"archive")
    reference = tmp_path / "bound-reference.json"
    reference.write_bytes(b"manifest")
    destination = tmp_path / "candidate"
    monkeypatch.setattr(module, "stage_root", lambda target: None)
    monkeypatch.setattr(module, "write_repo_docs", lambda *args, **kwargs: None)
    calls: list[list[str]] = []

    def record_run(command, *, cwd, check, **kwargs):
        calls.append(command)
        if "scripts/public_tree_manifest.py" in command:
            assert (destination / module.TYPED_EVIDENCE_PATH).read_bytes() == b"archive"
            assert (
                destination / module.TYPED_BOUND_REFERENCE_MANIFEST_PATH
            ).read_bytes() == b"manifest"

    monkeypatch.setattr(module.subprocess, "run", record_run)
    module.stage(
        destination,
        typed_evidence_archive=archive,
        typed_evidence_bound_reference_manifest=reference,
        anonymous_review=True,
    )
    assert any(command[-2:] == ["--bound-reference-manifest", str(reference)] for command in calls)


def test_bound_and_historical_references_are_mutually_exclusive(tmp_path: Path) -> None:
    module = _load_module()
    with pytest.raises(ValueError, match="Select one typed evidence reference"):
        module.stage(
            tmp_path / "candidate",
            typed_evidence_archive=tmp_path / "evidence.tar.gz",
            typed_evidence_reference_manifest=tmp_path / "historical.json",
            typed_evidence_bound_reference_manifest=tmp_path / "bound.json",
        )


def test_typed_reference_requires_archive(tmp_path: Path) -> None:
    module = _load_module()
    with pytest.raises(ValueError, match="requires a typed evidence archive"):
        module.stage(
            tmp_path / "candidate",
            typed_evidence_reference_manifest=tmp_path / "reference.json",
        )


@pytest.mark.parametrize(
    "release_mode", ["anonymous_review", "public_evidence_release", "identified_release"]
)
def test_release_with_typed_archive_requires_privacy_reference(
    tmp_path: Path, release_mode: str
) -> None:
    module = _load_module()
    destination = tmp_path / "candidate"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("preserved", encoding="utf-8")
    repository_url = (
        "https://github.com/example/sticks-artifact"
        if release_mode == "identified_release"
        else None
    )

    with pytest.raises(ValueError, match="typed evidence reference manifest"):
        module.stage(
            destination,
            repository_url=repository_url,
            typed_evidence_archive=tmp_path / "evidence.tar.gz",
            **{release_mode: True},
        )

    assert marker.read_text(encoding="utf-8") == "preserved"


@pytest.mark.parametrize(
    "release_mode", ["anonymous_review", "public_evidence_release", "identified_release"]
)
def test_release_rejects_c0045_series_without_privacy_gate(
    tmp_path: Path, release_mode: str
) -> None:
    module = _load_module()
    destination = tmp_path / "candidate"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("preserved", encoding="utf-8")
    typed_archive = (
        {"typed_evidence_archive": tmp_path / "evidence.tar.gz"}
        if release_mode == "public_evidence_release"
        else {}
    )
    repository_url = (
        "https://github.com/example/sticks-artifact"
        if release_mode == "identified_release"
        else None
    )

    with pytest.raises(ValueError, match="C0045 series archive requires a privacy review"):
        module.stage(
            destination,
            repository_url=repository_url,
            c0045_series_archive=tmp_path / "series.tar.gz",
            **typed_archive,
            **{release_mode: True},
        )

    assert marker.read_text(encoding="utf-8") == "preserved"


def test_c0045_series_docs_state_private_scope(tmp_path: Path) -> None:
    module = _load_module()
    module.write_repo_docs(tmp_path, repository_url=None, bundled_c0045_series=True)
    for name in (
        "README.md", "REVIEWER_GUIDE.md", "ARTIFACT_MANIFEST.md",
        "PUBLIC_REPOSITORY_SCOPE.md",
    ):
        document = (tmp_path / name).read_text(encoding="utf-8")
        assert "release/experiments/c0045_compute_effect_series/series.tar.gz" in document
        assert "verify_c0045_effect_series_archive" in document
        assert "pending semantic privacy approval" in document
        assert "does not execute a new QEMU campaign" in document


def test_c0045_series_docs_state_anonymous_approval(tmp_path: Path) -> None:
    module = _load_module()
    module.write_repo_docs(
        tmp_path,
        repository_url=None,
        bundled_c0045_series=True,
        anonymous_review=True,
    )
    document = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "C0045 compute-effect series (anonymous review)" in document
    assert "approves this archive for anonymous review only" in document
    assert "pending semantic privacy approval" not in document


def test_c0045_series_rejects_identified_release(tmp_path: Path) -> None:
    module = _load_module()
    with pytest.raises(ValueError, match="approved only for anonymous review"):
        module.stage(
            tmp_path / "candidate",
            repository_url="https://github.com/example/sticks",
            c0045_series_archive=tmp_path / "series.tar.gz",
            c0045_privacy_review=tmp_path / "review.json",
            identified_release=True,
        )


def test_c0045_series_public_docs_keep_effect_scope_explicit(tmp_path: Path) -> None:
    module = _load_module()
    module.write_repo_docs(
        tmp_path,
        repository_url=None,
        bundled_typed_evidence=True,
        bundled_c0045_series=True,
        public_evidence_release=True,
    )
    for name in (
        "README.md", "REVIEWER_GUIDE.md", "ARTIFACT_MANIFEST.md",
        "PUBLIC_REPOSITORY_SCOPE.md",
    ):
        document = (tmp_path / name).read_text(encoding="utf-8")
        assert "## C0045 compute-effect series" in document
        assert "This release includes the selected series" in document
        assert "does not execute a new QEMU campaign" in document
        assert "pending semantic privacy approval" not in document


def test_c0045_series_archive_is_copied_before_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    archive = tmp_path / "series.tar.gz"
    archive.write_bytes(b"sealed-series")
    destination = tmp_path / "candidate"
    monkeypatch.setattr(module, "stage_root", lambda target: None)
    monkeypatch.setattr(
        module, "write_repo_docs", lambda target, repository_url, **kwargs: None
    )
    commands: list[list[str]] = []

    def record_run(command, *, cwd, check, **kwargs):
        assert check is True
        commands.append(command)
        if "scripts/public_tree_manifest.py" in command:
            staged = destination / module.C0045_SERIES_ARCHIVE_PATH
            assert staged.read_bytes() == archive.read_bytes()

    monkeypatch.setattr(module.subprocess, "run", record_run)
    module.stage(destination, c0045_series_archive=archive)

    assert [command[2] for command in commands[:2]] == [
        "scripts.verify_c0045_effect_series_archive",
        "scripts.screen_c0045_series_privacy",
    ]
    assert (destination / module.C0045_SERIES_ARCHIVE_PATH).read_bytes() == b"sealed-series"


def test_private_candidate_docs_identify_release_boundary(tmp_path: Path) -> None:
    module = _load_module()
    module.write_repo_docs(tmp_path, repository_url=None, bundled_typed_evidence=True)
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "typed-run-evidence/c0010-c0026.tar.gz" in readme
    assert "screens changed bytes" in readme
    assert "pending content and privacy approval" in readme
    assert "does not rerun QEMU or certify historical fidelity" in readme


def test_public_evidence_docs_keep_receipt_scope_explicit(tmp_path: Path) -> None:
    module = _load_module()
    module.write_repo_docs(
        tmp_path,
        repository_url=None,
        bundled_typed_evidence=True,
        public_evidence_release=True,
    )
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "## Typed-run evidence" in readme
    assert "This release includes the selected archive" in readme
    assert "pending content and privacy approval" not in readme
    assert "private candidate" not in readme
    assert "Receipt source hashes identify the archived run source" in readme
    assert "does not rerun QEMU or certify historical fidelity" in readme


@pytest.mark.parametrize(
    "release_mode", ["anonymous_review", "public_evidence_release", "identified_release"]
)
def test_release_requires_archive(tmp_path: Path, release_mode: str) -> None:
    module = _load_module()
    repository_url = (
        "https://github.com/example/sticks" if release_mode == "identified_release" else None
    )
    with pytest.raises(ValueError, match="requires a typed evidence archive"):
        module.stage(
            tmp_path / "release",
            repository_url=repository_url,
            **{release_mode: True},
        )
    assert not (tmp_path / "release").exists()


def test_public_package_declares_reviewer_requirements_and_graph_semantics(
    tmp_path: Path,
) -> None:
    module = _load_module()
    module.write_repo_docs(tmp_path, repository_url=None)

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    required_headings = {
        "## Repository structure",
        "## Evaluation qualities",
        "## Basic information",
        "## Dependencies",
        "## Security considerations",
        "## Installation",
        "## Minimal test",
        "## Experiments",
        "## License",
    }

    assert required_headings <= set(readme.splitlines())
    assert "docs/REALIZATION_SPACE.md" in module.ROOT_FILES
    assert "docs/RECONSTRUCTION_ARCHITECTURE.md" in module.ROOT_FILES
    assert "docs/FACT_SEMANTICS.md" in module.ROOT_FILES


def test_qemu_reviewer_guide_and_isolated_runner_enter_public_package() -> None:
    module = _load_module()
    assert "docs/IAC_LIMITATIONS_ARM64.md" in module.ROOT_FILES

    scripts_ignore = module.ignore_for_directory("scripts")
    script_names = ["run_isolated_lab_campaign.py", "run_lab_campaign.py"]
    assert not (
        set(script_names)
        & scripts_ignore(str(module.STICKS_ROOT / "scripts"), script_names)
    )


def test_optional_qa_dependencies_are_shipped_and_distinguished(tmp_path: Path) -> None:
    module = _load_module()
    module.write_repo_docs(tmp_path, repository_url=None)
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "requirements-qa.txt" in module.ROOT_FILES
    assert "## Optional QA dependencies" in readme
    assert "pip install -r requirements-qa.txt" in readme
    assert "tests/test_legacy_infrastructure_paths.py" in readme
    assert "tests/test_qemu_network_serialization.py" in readme
    assert "tests/test_workbench_browser_state.py" in readme
    assert "not VM campaign qualification" in " ".join(readme.split())
    assert "real lab-run evidence" in readme
    assert 'STICKS_PYTHON="$PWD/.venv-qa/bin/python" bash run_review_check.sh' in readme
    assert "without installation or fallback" in readme


def test_optional_qa_profile_preserves_primary_lock_and_pins_extras() -> None:
    profile = (PROJECT_ROOT / "requirements-qa.txt").read_text().splitlines()
    requirements = [line for line in profile if line and not line.startswith("#")]
    assert requirements[0] == "-r requirements.txt"
    assert len(requirements[1:]) == 5
    assert all("==" in requirement for requirement in requirements[1:])
    assert "requests==2.34.2" in requirements
    primary = (PROJECT_ROOT / "requirements.lock").read_text()
    assert "requests==" not in primary
    assert ".venv-qa/" in (PROJECT_ROOT / ".gitignore").read_text().splitlines()


def test_python_package_readme_is_in_the_public_file_allowlist() -> None:
    module = _load_module()
    metadata = tomllib.loads((module.STICKS_ROOT / "pyproject.toml").read_text())
    assert metadata["project"]["readme"] in module.ROOT_FILES


def test_legacy_shadowray_host_executor_is_not_packaged(tmp_path: Path) -> None:
    module = _load_module()
    module.stage_root(tmp_path)

    assert not (
        tmp_path / "src/executors/simple_working_executors_shadowray.py"
    ).exists()
    assert (tmp_path / "scripts/screen_c0045_series_privacy.py").is_file()


def test_workbench_quickstart_is_shipped_and_linked(tmp_path: Path) -> None:
    module = _load_module()
    assert "docs/reviewer_quickstart.md" in module.ROOT_FILES
    module.write_repo_docs(tmp_path, repository_url=None)
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "scripts/run_realization_workbench.py" in readme
    assert "docs/reviewer_quickstart.md" in readme


def test_public_package_includes_the_documented_realization_workbench(tmp_path: Path) -> None:
    module = _load_module()
    module.stage_root(tmp_path)

    assert (tmp_path / "scripts" / "run_realization_workbench.py").is_file()
    assert (tmp_path / "web" / "realization-workbench" / "index.html").is_file()
    assert (tmp_path / "web" / "realization-workbench" / "app.js").is_file()


def test_public_package_includes_typed_outcome_auditor(tmp_path: Path) -> None:
    module = _load_module()
    module.stage_root(tmp_path)

    assert (tmp_path / "scripts" / "audit_typed_campaign_outcomes.py").is_file()
    assert (tmp_path / "scripts" / "verify_typed_evidence_archive.py").is_file()
    assert (tmp_path / "tests" / "test_audit_typed_campaign_outcomes.py").is_file()
    assert (tmp_path / "tests" / "test_verify_typed_evidence_archive.py").is_file()
