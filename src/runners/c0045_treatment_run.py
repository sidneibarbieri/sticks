"""Retain one prospective C0045 treatment separately from the source campaign."""

import hashlib
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from executors.lab_transport import detect_lab_infrastructure
from runners.c0045_compute_observer import C0045ComputeRequest
from runners.c0045_compute_study import STUDY_PATH, load_c0045_compute_study
from runners.c0045_runtime_contracts import (
    CONTRACT_PATH, c0045_treatment_registry, load_c0045_runtime_contract,
)
from runners.campaign_runner import C0045LiveObserverBinding, UnifiedCampaignRunner
from runners.capability_facts import Digest, FactScope, Identity, ImmutableRecord
from runners.capability_observations import _directory, _write_exclusive
from runners.lab_runtime_bootstrap import LabBootstrapOutcome, bootstrap_lab_authority
from runners.runtime_diagnostics import ProcessFailure, process_failure
from runners.runtime_invocation import RuntimeOccurrenceOutcome
from runners.runtime_journal import RuntimeJournalReference
from runners.runtime_step_contracts import RuntimeStepContract


class C0045TreatmentRecord(ImmutableRecord):
    """One selected cell, never a full ShadowRay campaign or four-arm result."""

    schema_version: Literal["c0045-prospective-treatment/v1"]
    campaign_id: Literal["0.shadowray"]
    run_id: Identity
    source_mode: Literal["naive_simulated"]
    treatment_mode: Literal["real_controlled"]
    study_sha256: Digest
    runtime_binding_sha256: Digest
    infrastructure_provider: str
    contract: RuntimeStepContract
    bootstrap: LabBootstrapOutcome | None
    outcome: RuntimeOccurrenceOutcome | None
    journal_references: tuple[RuntimeJournalReference, ...]
    status: Literal["planned", "observed", "failed", "error"]
    uncollected_controls: tuple[
        Literal["busy", "idle", "controller_only"], ...
    ] = ("busy", "idle", "controller_only")
    error_type: str | None = None
    error_message: str | None = None
    process_failure: ProcessFailure | None = None

    @model_validator(mode="after")
    def validate_evidence_boundary(self) -> Self:
        if self.contract.occurrence != 10 or self.contract.scope.run_id != self.run_id:
            raise ValueError("C0045 record differs from the selected occurrence")
        if self.status in {"observed", "failed"} and self.outcome is None:
            raise ValueError("Evaluated C0045 treatment requires an outcome")
        if self.status == "observed" and (
            not self.outcome.invocation.executor_completed
            or not any(
                fact.name == "compute:bounded_guest_cpu"
                for fact in self.outcome.authorizing_facts
            )
        ):
            raise ValueError("Observed C0045 treatment requires a granted CPU fact")
        if self.status == "failed" and self.outcome.authorizing_facts:
            raise ValueError("Failed C0045 treatment cannot grant facts")
        if self.status == "error" and (self.error_type is None or self.error_message is None):
            raise ValueError("C0045 error must retain its diagnostic")
        if self.status != "error" and (self.error_type is not None or self.error_message is not None):
            raise ValueError("Only C0045 errors may retain an exception diagnostic")
        return self


def _retain_record(record: C0045TreatmentRecord, run_root: Path, name: str) -> None:
    with _directory(None, str(run_root)) as root:
        _write_exclusive(root, name, record.model_dump_json().encode("utf-8"))


def run_c0045_treatment(output_dir: Path) -> tuple[C0045TreatmentRecord, Path]:
    """Run only the frozen treatment row; controls require separate cells."""
    study = load_c0045_compute_study()
    selected_registry = c0045_treatment_registry()
    runner = UnifiedCampaignRunner(study.campaign_id, output_dir, require_lab=True)
    run_root = output_dir / "c0045-prospective" / runner.run_id
    run_root.parent.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(exist_ok=False)
    provisional = FactScope(
        run_id=runner.run_id, environment_id=f"lab-{runner.run_id}",
        epoch="not-probed", locus="target",
        host_id=study.target_host_id, principal=study.target_principal,
    )
    contract = load_c0045_runtime_contract(provisional, selected_registry)
    record_fields = {
        "schema_version": "c0045-prospective-treatment/v1",
        "campaign_id": study.campaign_id,
        "run_id": runner.run_id,
        "source_mode": study.source_mode,
        "treatment_mode": study.prospective_mode,
        "study_sha256": hashlib.sha256(STUDY_PATH.read_bytes()).hexdigest(),
        "runtime_binding_sha256": hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
    }
    _retain_record(C0045TreatmentRecord(
        **record_fields, infrastructure_provider="", contract=contract,
        bootstrap=None, outcome=None, journal_references=(), status="planned",
    ), run_root, "plan.json")
    provider = ""
    bootstrap = None
    try:
        provider = detect_lab_infrastructure(study.campaign_id)
        if not provider:
            raise RuntimeError("C0045 treatment requires a reachable target guest")
        bootstrap = bootstrap_lab_authority(
            sut_profile_id=study.campaign_id,
            expected_host_id=study.target_host_id,
            principal=study.target_principal,
            run_id=runner.run_id,
            environment_id=provisional.environment_id,
            run_root=run_root,
            store=runner.fact_store,
        )
        contract = load_c0045_runtime_contract(bootstrap.scope, selected_registry)

        def request_for_process(selection):
            return C0045ComputeRequest(
                sut_profile_id=study.campaign_id,
                scope=contract.scope,
                nonce=selection.nonce,
                producer_occurrence=contract.occurrence,
                process_id=selection.process_id,
                command_sha256=selection.command_sha256,
            )

        outcome = runner.execute_contracted_occurrence(
            contract, {}, run_root=run_root, selected_registry=selected_registry,
            live_observer=C0045LiveObserverBinding(request_for_process),
        )
        status = "observed" if outcome.authorizing_facts else "failed"
        report = C0045TreatmentRecord(
            **record_fields, infrastructure_provider=provider,
            contract=contract, bootstrap=bootstrap, outcome=outcome,
            journal_references=tuple(runner.runtime_journal_references),
            status=status,
        )
        _retain_record(report, run_root, "summary.json")
        return report, run_root
    except Exception as error:
        try:
            _retain_record(C0045TreatmentRecord(
                **record_fields, infrastructure_provider=provider,
                contract=contract, bootstrap=bootstrap, outcome=None,
                journal_references=tuple(runner.runtime_journal_references),
                status="error", error_type=type(error).__name__,
                error_message=str(error), process_failure=process_failure(error),
            ), run_root, "summary.json")
        except Exception as retention_error:
            raise ExceptionGroup(
                "C0045 execution and summary retention both failed",
                [error, retention_error],
            ) from None
        raise
