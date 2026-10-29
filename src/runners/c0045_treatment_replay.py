"""Replay a retained C0045 treatment after the QEMU guest is gone."""

import hashlib
from pathlib import Path

from runners.c0045_compute_study import STUDY_PATH
from runners.c0045_runtime_contracts import (
    CONTRACT_PATH, c0045_treatment_registry, load_c0045_runtime_contract,
)
from runners.c0045_treatment_run import C0045TreatmentRecord
from runners.capability_authority import verify_registered_observation
from runners.capability_observations import (
    _directory, _read_record, verify_observation_reference,
)
from runners.runtime_journal import RuntimeJournalRecord


def _read_root_record(run_root: Path, filename: str) -> bytes:
    with _directory(None, str(run_root)) as directory:
        return _read_record(directory, filename)


def _verify_journal(record: C0045TreatmentRecord, run_root: Path) -> None:
    expected_phases = ("started", "executor_completed", "observed")
    if len(record.journal_references) != len(expected_phases):
        raise ValueError("C0045 treatment has an incomplete occurrence journal")
    for reference, phase in zip(record.journal_references, expected_phases):
        components = reference.record_path.split("/")
        if len(components) != 2 or components[0] != "runtime_journal":
            raise ValueError("C0045 journal reference has an unexpected path")
        with _directory(None, str(run_root)) as root:
            with _directory(root, "runtime_journal") as journal_dir:
                data = _read_record(journal_dir, components[1])
        if hashlib.sha256(data).hexdigest() != reference.record_sha256:
            raise ValueError("C0045 journal bytes differ from their receipt")
        journal = RuntimeJournalRecord.model_validate_json(data)
        if journal.phase != phase or journal.contract != record.contract:
            raise ValueError("C0045 journal differs from the selected occurrence")
        if phase == "observed" and (
            journal.observation_references != record.outcome.observation_references
            or journal.authorizing_facts != record.outcome.authorizing_facts
        ):
            raise ValueError("C0045 final journal differs from the treatment result")


def verify_c0045_treatment(run_root: Path) -> C0045TreatmentRecord:
    """Verify source, controller receipts and guest replies without live transport."""
    plan = C0045TreatmentRecord.model_validate_json(
        _read_root_record(run_root, "plan.json")
    )
    summary = C0045TreatmentRecord.model_validate_json(
        _read_root_record(run_root, "summary.json")
    )
    if plan.status != "planned" or plan.outcome is not None or plan.bootstrap is not None:
        raise ValueError("C0045 plan must precede guest acquisition")
    if (
        plan.run_id != summary.run_id
        or plan.study_sha256 != summary.study_sha256
        or plan.runtime_binding_sha256 != summary.runtime_binding_sha256
        or plan.contract.occurrence != summary.contract.occurrence
    ):
        raise ValueError("C0045 plan and summary differ in their frozen selection")
    if (
        summary.study_sha256 != hashlib.sha256(STUDY_PATH.read_bytes()).hexdigest()
        or summary.runtime_binding_sha256
        != hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    ):
        raise ValueError("C0045 result differs from the current frozen sources")
    selected = load_c0045_runtime_contract(
        summary.contract.scope, c0045_treatment_registry()
    )
    if plan.contract != load_c0045_runtime_contract(
        plan.contract.scope, c0045_treatment_registry()
    ):
        raise ValueError("C0045 plan differs from the frozen runtime contract")
    if summary.contract != selected:
        raise ValueError("C0045 result differs from the selected runtime contract")
    if summary.status not in {"observed", "failed"} or summary.bootstrap is None:
        raise ValueError("C0045 run has no completed target observation")
    if summary.infrastructure_provider == "":
        raise ValueError("C0045 result lacks a lab provider")
    if summary.uncollected_controls != ("busy", "idle", "controller_only"):
        raise ValueError("C0045 result omits uncollected control cells")
    bootstrap = summary.bootstrap
    if bootstrap.scope != selected.scope:
        raise ValueError("C0045 bootstrap differs from the treatment scope")
    discovery = verify_observation_reference(
        bootstrap.discovery_reference, run_root=run_root,
        expected_scope=selected.scope, expected_predicate="lifecycle-identity",
    )
    shell = verify_registered_observation(
        bootstrap.reference, run_root=run_root,
        expected_scope=selected.scope, expected_predicate="shell-nonce",
    )
    if (
        not discovery.passed or not shell.passed
        or tuple(fact.name for fact in bootstrap.facts) != ("lab:shell",)
        or bootstrap.facts[0].observation != bootstrap.reference
    ):
        raise ValueError("C0045 bootstrap lacks observed guest-shell authority")
    if len(summary.outcome.observation_references) != 1:
        raise ValueError("C0045 treatment requires exactly one live observation")
    reference = summary.outcome.observation_references[0]
    observed = verify_registered_observation(
        reference, run_root=run_root, expected_scope=selected.scope,
        expected_predicate="bounded-guest-cpu",
    )
    if summary.outcome.observations != (observed,):
        raise ValueError("C0045 result differs from its replayed observation")
    if (summary.status == "observed") != observed.passed:
        raise ValueError("C0045 status differs from the replayed guest effect")
    expected_fact_names = ("compute:bounded_guest_cpu",) if observed.passed else ()
    if tuple(fact.name for fact in summary.outcome.authorizing_facts) != expected_fact_names:
        raise ValueError("C0045 result differs from replayed product authority")
    if any(
        fact.observation != reference
        or fact.scope != selected.scope
        or fact.producer_occurrence != selected.occurrence
        or fact.content_sha256 != observed.content_sha256
        for fact in summary.outcome.authorizing_facts
    ):
        raise ValueError("C0045 granted fact differs from its observation")
    _verify_journal(summary, run_root)
    return summary
