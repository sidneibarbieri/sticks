#!/usr/bin/env python3
"""Verify retained C0045 integration journals, not historical campaign fidelity."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ARTIFACT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(ARTIFACT_ROOT / "src"), str(ARTIFACT_ROOT))

from runners.caldera_journal import CalderaJournalVerificationV2, verify_journal
from runners.runtime_campaign_report import parse_retained_campaign_report
from scripts.audit_typed_campaign_outcomes import verify_retained_observations
from scripts.screen_typed_evidence_privacy import screen_archive
from scripts.verify_typed_evidence_archive import extract_members

RUN_DIRECTORIES = ("c0045-r2", "c0045-r3")
EXPECTED_POPULATION = (5, 5, 0)


class RetainedRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class OccurrenceResult(RetainedRecord):
    occurrence: int = Field(strict=True, ge=1)
    technique_id: str
    mode: Literal["real_controlled", "naive_simulated"]
    status: Literal["observed", "simulated"]


class TeardownResult(RetainedRecord):
    caldera: Literal["not_created"]
    attacker: Literal["not_created"]
    target: Literal["not_created"] = Field(alias="target-linux-1")


class Qualification(RetainedRecord):
    schema_version: Literal["caldera-cold-integration-qualification/v1"] = Field(alias="schema")
    source_commit: str = Field(pattern=r"^(?:[0-9a-f]{8}|[0-9a-f]{40})$")
    campaign: Literal["0.shadowray"]
    mode: Literal["cold_integration_qualification"]
    pipeline_exit_code: Literal[0]
    journal_verification_exit_code: Literal[0]
    journal: CalderaJournalVerificationV2
    steps: tuple[OccurrenceResult, ...]
    teardown: TeardownResult
    scientific_scope: str = Field(min_length=1)
    repeated_run: str | None = None
    comparison: str | None = None


def verify_evidence_hashes(run_root: Path) -> int:
    """Require a complete file population and exact retained evidence bytes."""
    evidence = run_root / "evidence"
    manifest = json.loads((run_root / "evidence-sha256.json").read_text())
    files = {path.relative_to(evidence).as_posix(): path
             for path in evidence.rglob("*") if path.is_file()}
    if not isinstance(manifest, dict) or set(manifest) != set(files):
        raise ValueError("Evidence population differs from its hash manifest")
    for relative, path in files.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest[relative]:
            raise ValueError("Retained evidence digest differs: " + relative)
    return len(files)


def verify_run(run_root: Path) -> tuple[dict, tuple]:
    """Recheck observations and dispatch bindings without contacting a VM."""
    expected_entries = {"evidence", "qualification.json", "evidence-sha256.json"}
    if {path.name for path in run_root.iterdir()} != expected_entries:
        raise ValueError("Integration run contains undeclared root entries")
    qualification = Qualification.model_validate_json(
        (run_root / "qualification.json").read_bytes()
    )
    file_count = verify_evidence_hashes(run_root)
    evidence = run_root / "evidence"
    summaries = tuple((evidence / "runtime-v2").glob("*/summary.json"))
    if len(summaries) != 1:
        raise ValueError("Integration run requires exactly one campaign summary")
    report = parse_retained_campaign_report(summaries[0].read_text())
    if report.campaign_id != qualification.campaign or len(report.steps) != 10:
        raise ValueError("Integration campaign or population differs")
    if (report.effects_observed, report.simulated, report.failed) != EXPECTED_POPULATION:
        raise ValueError("Integration outcomes exceed the declared fixture scope")
    actual_steps = tuple(OccurrenceResult(
        occurrence=step.contract.occurrence,
        technique_id=step.contract.technique_id,
        mode=step.contract.mode,
        status=step.status,
    ) for step in report.steps)
    if actual_steps != qualification.steps:
        raise ValueError("Qualification steps differ from retained outcomes")
    verify_retained_observations(report, summaries[0].parent)
    journal = verify_journal(evidence)
    if journal != qualification.journal:
        raise ValueError("Qualification journal differs from the verified journal")
    contracts = tuple((
        step.contract.occurrence, step.contract.technique_id,
        step.contract.mode, step.contract.executor_id,
        step.contract.executor_sha256, step.contract.scope.locus,
        step.contract.scope.principal,
    ) for step in report.steps)
    return {
        "run": run_root.name, "source_commit": qualification.source_commit,
        "run_id": report.run_id,
        "target_boot_id": next(step.contract.scope.epoch for step in report.steps
                               if step.status == "observed"),
        "evidence_files": file_count, "journal": journal.model_dump(mode="json"),
        "teardown": qualification.teardown.model_dump(by_alias=True),
    }, contracts


def require_distinct_runs(runs: list[dict]) -> None:
    """A copied run or a reused target boot is not a second cold repetition."""
    for identity in ("run_id", "target_boot_id"):
        if len({run[identity] for run in runs}) != len(RUN_DIRECTORIES):
            raise ValueError("Repeated integrations share the same " + identity)


def verify_archive(archive_path: Path, reference_root: Path | None = None) -> dict:
    """Reject unsafe archives and verify both independent retained runs."""
    with tempfile.TemporaryDirectory(prefix="sticks-integration-") as temporary:
        destination = Path(temporary)
        with tarfile.open(archive_path, "r:gz") as archive:
            extract_members(archive, destination, RUN_DIRECTORIES)
        results = [verify_run(destination / name) for name in RUN_DIRECTORIES]
    runs = [result[0] for result in results]
    require_distinct_runs(runs)
    if results[0][1] != results[1][1]:
        raise ValueError("Repeated runs differ in their declared executor contracts")
    if runs[0]["source_commit"] != runs[1]["source_commit"]:
        raise ValueError("Repeated runs declare different source revisions")
    if reference_root is not None:
        screen = screen_archive(
            archive_path, reference_root=reference_root,
            campaign_directories=RUN_DIRECTORIES,
            lab_users=frozenset({b"rayuser"}),
        )
        if not screen.passed:
            raise ValueError("Integration archive fails the privacy screen: "
                             + ", ".join(sorted(screen.findings)))
    return {
        "schema": "caldera-integration-archive-verification/v1",
        "runs": runs, "executor_contract_fields_match": True,
        "privacy_screen_passed": True if reference_root is not None else None,
        "scope": "Retained fixture effects, journals and teardown records; "
                 "not full semantic sealing, historical fidelity or independent-host replication",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_archive(args.archive, args.reference_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
