#!/usr/bin/env python3
"""
Unified Campaign Runner - Orchestrates Campaign → SUT → Executor → Evidence pipeline.
"""

import argparse
import json
import os
import sys
import traceback
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Set
from uuid import uuid4

# Extend path before project imports so the src layout resolves correctly.
sys.path.insert(0, str(Path(__file__).parent.parent))

from executors.campaign_bootstrap import bootstrap_campaign_executors  # noqa: E402
from executors.c0045_compute_executor import C0045ProcessSelection  # noqa: E402
from executors.c0045_trace_executor import C0045TraceSelection  # noqa: E402
from executors.c0045_readonly_commands import TraceKind  # noqa: E402
from executors.executor_registry import (  # noqa: E402
    execute_technique,
    registry,
)
from executors.lab_transport import (  # noqa: E402
    detect_lab_infrastructure,
)
from executors.models import (  # noqa: E402
    ArtifactMetadata,
    CampaignEvidence,
    ExecutionFidelity,
    ExecutionMode,
    FidelityAssessment,
    Platform,
    TechniqueEvidence,
)
from executors.registry_initializer import initialize_registry  # noqa: E402
from apply_sut_profile import apply_step_sut_delta  # noqa: E402
from loaders.campaign_loader import (  # noqa: E402
    list_campaigns,
    load_campaign,
    load_sut_profile,
    validate_campaign_sut_pair,
)
from runners.capability_facts import CapabilityFact, FactScope  # noqa: E402
from runners.capability_store import CapabilityStore  # noqa: E402
from runners.capability_authority import (  # noqa: E402
    LabShellRequest,
    acquire_registered_observation,
    verify_registered_observation,
)
from runners.runtime_invocation import (
    RuntimeOccurrenceOutcome,
    RuntimeReadinessError,
    invoke_runtime_step,
)  # noqa: E402
from runners.runtime_step_contracts import RuntimeStepContract  # noqa: E402
from runners.runtime_diagnostics import process_failure  # noqa: E402
from runners.c0026_capability_observers import C0026EffectRequest, effect_request  # noqa: E402
from runners.c0010_http_observer import C0010HttpRequest  # noqa: E402
from runners.c0045_compute_observer import C0045ComputeRequest  # noqa: E402
from runners.c0045_api_observer import C0045ApiRequest  # noqa: E402
from runners.c0045_fixture_observer import C0045FixtureRequest  # noqa: E402
from runners.c0045_trace_observer import C0045TraceRequest  # noqa: E402
from runners.c0045_full_runtime_contracts import load_c0045_full_runtime_contracts  # noqa: E402
from runners.c0010_controller_observers import (  # noqa: E402
    C0010ControllerRequest,
    controller_request,
)
from runners.c0010_guest_observer import (
    C0010TransferRequest,
    require_c0010_fixture_readiness,
)  # noqa: E402
from runners.c0010_runtime_contracts import load_c0010_runtime_contracts  # noqa: E402
from runners.caldera_campaign_support import SUPPORTED_CALDERA_CAMPAIGNS  # noqa: E402
from runners.runtime_journal import RuntimeJournalRecord, retain_runtime_record  # noqa: E402
from runners.lab_runtime_bootstrap import (  # noqa: E402
    bootstrap_lab_authority,
    qualify_declared_lab_topology,
)
from runners.c0026_runtime_contracts import load_c0026_runtime_contracts  # noqa: E402
from runners.costaricto_capability_observers import (  # noqa: E402
    CostaRictoEffectRequest,
    costaricto_effect_request,
)
from runners.costaricto_runtime_contracts import load_costaricto_runtime_contracts  # noqa: E402
from runners.lab_campaign_support import require_live_campaign  # noqa: E402
from runners.runtime_campaign_report import (
    RuntimeCampaignReport,
    RuntimeCampaignStep,
    retain_campaign_report,
)  # noqa: E402

initialize_registry()

# Base capabilities always available on the host (no VM required)
BASE_CAPABILITIES = frozenset(
    {
        "resources:staging_directory",
        "resources:openssl_available",
        "network:ssh_available",
        "network:http_available",
    }
)
DEBUG_ENABLED = os.environ.get("STICKS_DEBUG") == "1"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HOME_DIR = Path.home()


@dataclass(frozen=True)
class LiveObserverBinding:
    """Acquire one registered observation before a short-lived service exits."""

    authority_id: str
    request_for_port: Callable[[int], C0010HttpRequest]


@dataclass(frozen=True)
class C0045LiveObserverBinding:
    """Build the registered request from the executor's live process selection."""

    request_for_process: Callable[[C0045ProcessSelection], C0045ComputeRequest]
    authority_id: str = "c0045-compute"


@dataclass(frozen=True)
class C0045TraceLiveObserverBinding:
    """Build a registered trace request from the selected executor handoff."""

    kind: TraceKind
    request_for_trace: Callable[[C0045TraceSelection], C0045TraceRequest]

    @property
    def authority_id(self) -> str:
        return "c0045-" + self.kind


class UnifiedCampaignRunner:
    """
    Orchestrates Campaign → SUT → Executor → Evidence pipeline.

    Loads validated Campaign and SUTProfile, executes each step in order,
    tracks capabilities, and produces structured CampaignEvidence.
    """

    def __init__(
        self,
        campaign_id: str,
        output_dir: Optional[Path] = None,
        *,
        require_lab: bool = False,
    ):
        bootstrap_campaign_executors(campaign_id)

        self.campaign_id = campaign_id
        self.campaign = load_campaign(campaign_id)
        self.sut = load_sut_profile(self.campaign.sut_profile_id)

        self.accumulated_capabilities: Set[str] = set(BASE_CAPABILITIES)
        self.run_id = uuid4().hex
        self.fact_store = CapabilityStore()
        self.runtime_invocations = []
        self.runtime_journal_references = []
        self.runtime_product_revalidations = {}
        self._load_sut_declarations()
        self.output_dir = Path(output_dir) if output_dir else Path("runs/evidence")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.require_lab = require_lab
        self._lab_topology = None

    def _load_sut_declarations(self) -> None:
        """Retain declared lab shell intent without granting operational access."""
        for host_id, host in self.sut.hosts.items():
            has_weak_creds = any(
                w.weakness_type in {"weak_credentials", "weak_ssh_password"}
                for w in host.deliberate_weaknesses
            )
            has_ssh = any(s.name == "ssh" for s in host.services)
            if has_weak_creds and has_ssh:
                for user in host.users:
                    self.fact_store.add_declaration(
                        CapabilityFact(
                            name="lab:shell",
                            origin="profile_declaration",
                            scope=FactScope(
                                run_id=self.run_id,
                                environment_id=self.sut.campaign_id,
                                epoch="not-started",
                                locus="target",
                                host_id=host_id,
                                principal=user.username,
                            ),
                            producer_occurrence=None,
                            observation=None,
                        )
                    )

    def execute_contracted_occurrence(
        self,
        contract: RuntimeStepContract,
        observer_requests: dict[
            str,
            LabShellRequest
            | C0026EffectRequest
            | C0010ControllerRequest
            | C0010TransferRequest
            | CostaRictoEffectRequest
            | C0045ApiRequest
            | C0045FixtureRequest,
        ],
        *,
        run_root: Path,
        selected_registry=None,
        live_observer: LiveObserverBinding
        | C0045LiveObserverBinding
        | C0045TraceLiveObserverBinding
        | None = None,
    ) -> RuntimeOccurrenceOutcome:
        """Execute one selected occurrence with independent registered observations."""
        steps = [
            step for step in self.campaign.steps if step.order == contract.occurrence
        ]
        if (
            contract.campaign_id != self.campaign_id
            or contract.scope.run_id != self.run_id
            or len(steps) != 1
            or steps[0].technique_id != contract.technique_id
        ):
            raise ValueError(
                "Runtime contract does not identify this runner occurrence"
            )
        live_authorities = {live_observer.authority_id} if live_observer else set()
        if set(observer_requests) & live_authorities or set(
            observer_requests
        ) | live_authorities != set(contract.observers):
            raise ValueError(
                "Observer requests must exactly match the selected contract"
            )
        if contract.mode == "naive_simulated" and contract.observers:
            raise ValueError("Simulated execution cannot grant observed products")
        for request in observer_requests.values():
            if (
                request.scope != contract.scope
                or request.sut_profile_id != self.sut.campaign_id
            ):
                raise ValueError(
                    "Observer request differs from the selected target scope"
                )
        invocation = None
        observations, references, granted, simulated = [], [], [], []
        live_result = None
        consumed = tuple(
            fact.observation
            for requirement in contract.requirements
            if (fact := self.fact_store.match(requirement)) is not None
            and fact.observation is not None
        )

        def checkpoint(phase, error=None):
            record = RuntimeJournalRecord(
                schema_version="runtime-occurrence/v2",
                phase=phase,
                contract=contract,
                invocation=invocation,
                observation_references=tuple(references),
                authorizing_facts=tuple(granted),
                simulated_facts=tuple(simulated),
                consumed_references=consumed,
                revalidation_references=self.runtime_product_revalidations.get(
                    contract.occurrence, ()
                ),
                error_type=type(error).__name__ if error is not None else None,
                error_message=str(error) if error is not None else None,
                process_failure=process_failure(error),
            )
            retained = retain_runtime_record(record, run_root=run_root)
            self.runtime_journal_references.append(retained)

        checkpoint("started")
        try:

            def capture_live_observation(
                value: int | C0045ProcessSelection | C0045TraceSelection,
            ) -> bool:
                nonlocal live_result
                if live_observer is None or live_result is not None:
                    raise ValueError(
                        "Live observation must be configured and called once"
                    )
                if isinstance(live_observer, C0045TraceLiveObserverBinding):
                    if (
                        not isinstance(value, C0045TraceSelection)
                        or value.kind != live_observer.kind
                    ):
                        raise ValueError(
                            "C0045 trace handoff differs from the selected kind"
                        )
                    request = live_observer.request_for_trace(value)
                elif isinstance(live_observer, C0045LiveObserverBinding):
                    if not isinstance(value, C0045ProcessSelection):
                        raise ValueError(
                            "C0045 live observer requires a process selection"
                        )
                    request = live_observer.request_for_process(value)
                else:
                    if type(value) is not int:
                        raise ValueError(
                            "C0010 live observer requires a controller port"
                        )
                    request = live_observer.request_for_port(value)
                if (
                    request.scope != contract.scope
                    or request.sut_profile_id != self.sut.campaign_id
                ):
                    raise ValueError(
                        "Live observer request differs from selected scope"
                    )
                if (
                    getattr(request, "producer_occurrence", contract.occurrence)
                    != contract.occurrence
                ):
                    raise ValueError(
                        "Live observer request differs from selected occurrence"
                    )
                reference = acquire_registered_observation(
                    live_observer.authority_id,
                    request,
                    run_root=run_root,
                )
                observed = verify_registered_observation(
                    reference,
                    run_root=run_root,
                    expected_scope=contract.scope,
                    expected_predicate=reference.predicate_id,
                )
                references.append(reference)
                observations.append(observed)
                live_result = (reference, observed)
                return observed.passed

            invocation = invoke_runtime_step(
                contract,
                self.fact_store,
                selected_registry if selected_registry is not None else registry,
                sut_profile_id=self.sut.campaign_id,
                live_observer=capture_live_observation if live_observer else None,
            )
            if live_observer and live_result is None:
                raise RuntimeError("Selected executor did not call its live observer")
            self.runtime_invocations.append((contract, invocation))
            checkpoint("executor_completed")
            if invocation.executor_completed and contract.mode == "naive_simulated":
                for name in invocation.declared_products:
                    fact = CapabilityFact(
                        name=name,
                        origin="simulation",
                        scope=contract.scope,
                        producer_occurrence=contract.occurrence,
                        observation=None,
                    )
                    self.fact_store.add_simulation(fact)
                    simulated.append(fact)
                checkpoint("simulated")
            if invocation.executor_completed:
                for authority_id in contract.observers:
                    if live_observer and authority_id == live_observer.authority_id:
                        reference, observed = live_result
                    else:
                        reference = acquire_registered_observation(
                            authority_id,
                            observer_requests[authority_id],
                            run_root=run_root,
                        )
                        observed = verify_registered_observation(
                            reference,
                            run_root=run_root,
                            expected_scope=contract.scope,
                            expected_predicate=reference.predicate_id,
                        )
                        observations.append(observed)
                        references.append(reference)
                    granted.extend(
                        self.fact_store.add_observed(
                            reference,
                            run_root=run_root,
                            expected_scope=contract.scope,
                            expected_predicate=reference.predicate_id,
                        )
                    )
                    checkpoint("observed")
        except Exception as error:
            try:
                checkpoint("error", error)
            except Exception as retention_error:
                raise ExceptionGroup(
                    "Runtime and journal retention both failed",
                    [error, retention_error],
                ) from None
            raise
        return RuntimeOccurrenceOutcome(
            invocation=invocation,
            observations=tuple(observations),
            observation_references=tuple(references),
            authorizing_facts=tuple(granted),
            simulated_facts=tuple(simulated),
            consumed_references=consumed,
        )

    def _runtime_campaign_report(
        self, steps, bootstrap, error=None
    ) -> RuntimeCampaignReport:
        return RuntimeCampaignReport(
            schema_version="runtime-campaign/v2",
            campaign_id=self.campaign_id,
            run_id=self.run_id,
            infrastructure_provider=self._infrastructure_provider,
            bootstrap=bootstrap,
            topology=self._lab_topology,
            steps=tuple(steps),
            runtime_facts=self.fact_store.snapshot(),
            journal_references=tuple(self.runtime_journal_references),
            error_type=type(error).__name__ if error is not None else None,
            error_message=str(error) if error is not None else None,
            process_failure=process_failure(error),
        )

    def _refresh_guest_authority(self, scope, run_root):
        request = LabShellRequest(
            sut_profile_id=self.sut.campaign_id, scope=scope, nonce=uuid4().hex
        )
        reference = acquire_registered_observation(
            "lab-shell", request, run_root=run_root
        )
        observed = verify_registered_observation(
            reference,
            run_root=run_root,
            expected_scope=scope,
            expected_predicate="shell-nonce",
        )
        if not observed.passed:
            self.fact_store.invalidate(scope)
            raise RuntimeReadinessError(
                "Current guest no longer matches the bound lifecycle scope"
            )
        self.fact_store.add_observed(
            reference,
            run_root=run_root,
            expected_scope=scope,
            expected_predicate="shell-nonce",
        )

    def _refresh_product_authority(self, contract, run_root):
        retained = []
        self.runtime_product_revalidations[contract.occurrence] = ()
        for requirement in contract.requirements:
            if requirement.name == "lab:shell":
                continue
            original = self.fact_store.match(requirement)
            if original is None:
                continue
            if original.content_sha256 is None or original.producer_occurrence is None:
                self.fact_store.invalidate_requirement(requirement)
                raise RuntimeReadinessError(
                    "Product lacks a bound digest or producer occurrence"
                )
            request = effect_request(
                original.observation.authority_id,
                requirement.scope,
                uuid4().hex,
                original.producer_occurrence,
                consumer_occurrence=contract.occurrence,
                revalidated_reference=original.observation,
            )
            reference = acquire_registered_observation(
                original.observation.authority_id, request, run_root=run_root
            )
            retained.append(reference)
            self.runtime_product_revalidations[contract.occurrence] = tuple(retained)
            current = verify_registered_observation(
                reference,
                run_root=run_root,
                expected_scope=requirement.scope,
                expected_predicate=request.predicate_id,
            )
            if not current.passed or current.content_sha256 != original.content_sha256:
                self.fact_store.invalidate_requirement(requirement)
                raise RuntimeReadinessError(
                    "Product bytes changed after their authorizing observation"
                )

    def _run_contracted_c0026(self) -> RuntimeCampaignReport:
        run_root = self.output_dir / "runtime-v2" / self.run_id
        run_root.mkdir(parents=True, exist_ok=False)
        self.evidence_dir = run_root
        self._infrastructure_provider = detect_lab_infrastructure(self.sut.campaign_id)
        provisional = FactScope(
            run_id=self.run_id,
            environment_id=f"lab-{self.run_id}",
            epoch="not-probed",
            locus="target",
            host_id="target-linux-1",
            principal="ubuntu",
        )
        contracts = load_c0026_runtime_contracts(provisional, registry)
        steps = [
            RuntimeCampaignStep(contract=contract, status="not_run", outcome=None)
            for contract in contracts
        ]
        retain_campaign_report(
            self._runtime_campaign_report(steps, None),
            run_root=run_root,
            filename="plan.json",
        )
        try:
            if not self._infrastructure_provider:
                raise RuntimeError(
                    "C0026 typed runtime requires a reachable guest; host fallback is unavailable"
                )
            bootstrap = bootstrap_lab_authority(
                sut_profile_id=self.sut.campaign_id,
                expected_host_id="target-linux-1",
                principal="ubuntu",
                run_id=self.run_id,
                environment_id=provisional.environment_id,
                run_root=run_root,
                store=self.fact_store,
            )
            contracts = load_c0026_runtime_contracts(bootstrap.scope, registry)
        except Exception as error:
            report = self._runtime_campaign_report(steps, None, error)
            retain_campaign_report(report, run_root=run_root, filename="summary.json")
            raise
        for index, contract in enumerate(contracts):
            try:
                if contract.mode == "real_controlled":
                    self._refresh_guest_authority(contract.scope, run_root)
                    self._refresh_product_authority(contract, run_root)
                input_name = {
                    "T1560.001": "collection:verified",
                    "T1030": "archive:verified",
                }.get(contract.technique_id)
                input_fact = next(
                    (
                        self.fact_store.match(requirement)
                        for requirement in contract.requirements
                        if requirement.name == input_name
                    ),
                    None,
                )
                requests = {
                    authority: effect_request(
                        authority,
                        contract.scope,
                        uuid4().hex,
                        contract.occurrence,
                        input_fact.content_sha256 if input_fact is not None else None,
                    )
                    for authority in contract.observers
                }
                outcome = self.execute_contracted_occurrence(
                    contract, requests, run_root=run_root
                )
                passed = outcome.invocation.executor_completed and (
                    contract.mode == "naive_simulated"
                    or bool(outcome.observations)
                    and all(item.passed for item in outcome.observations)
                )
                status = (
                    ("simulated" if contract.mode == "naive_simulated" else "observed")
                    if passed
                    else "failed"
                )
                steps[index] = RuntimeCampaignStep(
                    contract=contract,
                    status=status,
                    outcome=outcome,
                    revalidation_references=self.runtime_product_revalidations.get(
                        contract.occurrence, ()
                    ),
                )
            except Exception as error:
                steps[index] = RuntimeCampaignStep(
                    contract=contract,
                    status="blocked"
                    if isinstance(error, RuntimeReadinessError)
                    else "error",
                    outcome=None,
                    error_type=type(error).__name__,
                    error_message=str(error),
                    process_failure=process_failure(error),
                    revalidation_references=self.runtime_product_revalidations.get(
                        contract.occurrence, ()
                    ),
                )
        report = self._runtime_campaign_report(steps, bootstrap)
        retain_campaign_report(report, run_root=run_root, filename="summary.json")
        print(
            f"[RUNTIME] {report.total_techniques} occurrences: {report.effects_observed} observed, "
            f"{report.simulated} simulated, {report.failed} failed or blocked"
        )
        return report

    def _c0010_observer_requests(
        self,
        contract: RuntimeStepContract,
    ) -> dict[str, C0010ControllerRequest | C0010TransferRequest]:
        requests = {}
        for authority_id in contract.observers:
            if authority_id in {"c0010-payload", "c0010-page", "c0010-tool"}:
                requests[authority_id] = controller_request(
                    authority_id,
                    contract.scope,
                    uuid4().hex,
                    contract.occurrence,
                )
            elif authority_id == "c0010-transfer":
                requests[authority_id] = C0010TransferRequest(
                    sut_profile_id="0.c0010",
                    scope=contract.scope,
                    nonce=uuid4().hex,
                    producer_occurrence=9,
                )
            elif authority_id != "c0010-http":
                raise ValueError("Unknown C0010 observation authority")
        return requests

    def _c0010_live_observer(
        self,
        contract: RuntimeStepContract,
    ) -> LiveObserverBinding | None:
        if contract.observers != ("c0010-http",):
            return None

        def request_for_port(port: int) -> C0010HttpRequest:
            return C0010HttpRequest(
                sut_profile_id="0.c0010",
                scope=contract.scope,
                nonce=uuid4().hex,
                producer_occurrence=4,
                port=port,
            )

        return LiveObserverBinding("c0010-http", request_for_port)

    def _run_contracted_c0010(self) -> RuntimeCampaignReport:
        run_root = self.output_dir / "runtime-v2" / self.run_id
        run_root.mkdir(parents=True, exist_ok=False)
        self.evidence_dir = run_root
        self._infrastructure_provider = detect_lab_infrastructure(self.sut.campaign_id)
        provisional = FactScope(
            run_id=self.run_id,
            environment_id=f"lab-{self.run_id}",
            epoch="not-probed",
            locus="target",
            host_id="target-linux-1",
            principal="ubuntu",
        )
        contracts = load_c0010_runtime_contracts(provisional, registry)
        steps = [
            RuntimeCampaignStep(contract=contract, status="not_run", outcome=None)
            for contract in contracts
        ]
        retain_campaign_report(
            self._runtime_campaign_report(steps, None),
            run_root=run_root,
            filename="plan.json",
        )
        try:
            if not self._infrastructure_provider:
                raise RuntimeError("C0010 typed runtime requires a reachable guest")
            if self.require_lab:
                self._lab_topology = qualify_declared_lab_topology(self.sut.campaign_id)
            if Path.cwd().resolve() != PROJECT_ROOT:
                raise RuntimeError(
                    "C0010 controller staging requires the artifact working directory"
                )
            bootstrap = bootstrap_lab_authority(
                sut_profile_id=self.sut.campaign_id,
                expected_host_id="target-linux-1",
                principal="ubuntu",
                run_id=self.run_id,
                environment_id=provisional.environment_id,
                run_root=run_root,
                store=self.fact_store,
            )
            contracts = load_c0010_runtime_contracts(bootstrap.scope, registry)
            readiness = require_c0010_fixture_readiness(bootstrap.scope, uuid4().hex)
            (run_root / "profile-fixture-readiness.json").write_text(
                readiness.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        except Exception as error:
            retain_campaign_report(
                self._runtime_campaign_report(steps, None, error),
                run_root=run_root,
                filename="summary.json",
            )
            raise
        for index, contract in enumerate(contracts):
            try:
                if (
                    contract.mode == "real_controlled"
                    and contract.scope.locus == "target"
                ):
                    self._refresh_guest_authority(contract.scope, run_root)
                outcome = self.execute_contracted_occurrence(
                    contract,
                    self._c0010_observer_requests(contract),
                    run_root=run_root,
                    live_observer=self._c0010_live_observer(contract),
                )
                passed = outcome.invocation.executor_completed and (
                    contract.mode == "naive_simulated"
                    or bool(outcome.observations)
                    and all(item.passed for item in outcome.observations)
                )
                status = (
                    ("simulated" if contract.mode == "naive_simulated" else "observed")
                    if passed
                    else "failed"
                )
                steps[index] = RuntimeCampaignStep(
                    contract=contract, status=status, outcome=outcome
                )
            except Exception as error:
                steps[index] = RuntimeCampaignStep(
                    contract=contract,
                    status="blocked"
                    if isinstance(error, RuntimeReadinessError)
                    else "error",
                    outcome=None,
                    error_type=type(error).__name__,
                    error_message=str(error),
                    process_failure=process_failure(error),
                )
        report = self._runtime_campaign_report(steps, bootstrap)
        retain_campaign_report(report, run_root=run_root, filename="summary.json")
        return report

    def _run_contracted_costaricto(self) -> RuntimeCampaignReport:
        """Run all ten rows while certifying only bounded guest observations."""
        run_root = self.output_dir / "runtime-v2" / self.run_id
        run_root.mkdir(parents=True, exist_ok=False)
        self.evidence_dir = run_root
        self._infrastructure_provider = detect_lab_infrastructure(self.sut.campaign_id)
        provisional = FactScope(
            run_id=self.run_id,
            environment_id=f"lab-{self.run_id}",
            epoch="not-probed",
            locus="target",
            host_id="target-linux-1",
            principal="reconuser",
        )
        contracts = load_costaricto_runtime_contracts(provisional, registry)
        steps = [
            RuntimeCampaignStep(contract=contract, status="not_run", outcome=None)
            for contract in contracts
        ]
        retain_campaign_report(
            self._runtime_campaign_report(steps, None),
            run_root=run_root,
            filename="plan.json",
        )
        try:
            if not self._infrastructure_provider:
                raise RuntimeError(
                    "CostaRicto typed runtime requires a reachable guest"
                )
            bootstrap = bootstrap_lab_authority(
                sut_profile_id=self.sut.campaign_id,
                expected_host_id="target-linux-1",
                principal="reconuser",
                run_id=self.run_id,
                environment_id=provisional.environment_id,
                run_root=run_root,
                store=self.fact_store,
            )
            contracts = load_costaricto_runtime_contracts(bootstrap.scope, registry)
        except Exception as error:
            retain_campaign_report(
                self._runtime_campaign_report(steps, None, error),
                run_root=run_root,
                filename="summary.json",
            )
            raise
        for index, contract in enumerate(contracts):
            try:
                if contract.mode == "real_controlled":
                    self._refresh_guest_authority(contract.scope, run_root)
                requests = {
                    authority: costaricto_effect_request(
                        authority,
                        contract.scope,
                        uuid4().hex,
                        contract.occurrence,
                    )
                    for authority in contract.observers
                }
                outcome = self.execute_contracted_occurrence(
                    contract,
                    requests,
                    run_root=run_root,
                )
                passed = outcome.invocation.executor_completed and (
                    contract.mode == "naive_simulated"
                    or bool(outcome.observations)
                    and all(item.passed for item in outcome.observations)
                )
                status = (
                    ("simulated" if contract.mode == "naive_simulated" else "observed")
                    if passed
                    else "failed"
                )
                steps[index] = RuntimeCampaignStep(
                    contract=contract,
                    status=status,
                    outcome=outcome,
                )
            except Exception as error:
                steps[index] = RuntimeCampaignStep(
                    contract=contract,
                    status="blocked"
                    if isinstance(error, RuntimeReadinessError)
                    else "error",
                    outcome=None,
                    error_type=type(error).__name__,
                    error_message=str(error),
                    process_failure=process_failure(error),
                )
        report = self._runtime_campaign_report(steps, bootstrap)
        retain_campaign_report(report, run_root=run_root, filename="summary.json")
        return report

    def _c0045_observer_requests(self, contract: RuntimeStepContract) -> dict:
        """Construct the non-live observer requests for a single C0045 row."""
        scope = contract.scope
        if contract.observers == ("c0045-api",):
            return {
                "c0045-api": C0045ApiRequest(
                    sut_profile_id="0.shadowray",
                    scope=scope,
                    nonce=uuid4().hex,
                    producer_occurrence=contract.occurrence,
                )
            }
        fixture_predicates = {
            "c0045-toolkit": "toolkit-staged",
            "c0045-transfer": "loopback-transfer",
        }
        if len(contract.observers) == 1 and contract.observers[0] in fixture_predicates:
            authority_id = contract.observers[0]
            return {
                authority_id: C0045FixtureRequest(
                    sut_profile_id="0.shadowray",
                    predicate_id=fixture_predicates[authority_id],
                    producer_occurrence=contract.occurrence,
                    nonce=uuid4().hex,
                    scope=scope,
                )
            }
        if contract.observers in {(), ("c0045-python",), ("c0045-network",)}:
            return {}
        raise ValueError("Unknown C0045 observation authority")

    def _c0045_live_observer(
        self,
        contract: RuntimeStepContract,
    ) -> C0045TraceLiveObserverBinding | None:
        """Attach live retained-trace acquisition only to reviewed read-only rows."""
        trace_kind = {
            ("c0045-python",): "python",
            ("c0045-network",): "network",
        }.get(contract.observers)
        if trace_kind is None:
            return None

        def request_for_trace(selection: C0045TraceSelection) -> C0045TraceRequest:
            return C0045TraceRequest(
                sut_profile_id="0.shadowray",
                kind=trace_kind,
                producer_occurrence=contract.occurrence,
                nonce=selection.nonce,
                scope=contract.scope,
            )

        return C0045TraceLiveObserverBinding(
            kind=trace_kind, request_for_trace=request_for_trace
        )

    def _apply_c0045_step_delta(
        self, contract: RuntimeStepContract, run_root: Path
    ) -> None:
        """Apply and retain the declared precondition before its typed occurrence."""
        step = self.campaign.steps[contract.occurrence - 1]
        if step.order != contract.occurrence:
            raise ValueError("C0045 contract differs from its source occurrence")
        if step.sut_delta is None:
            return
        result = apply_step_sut_delta(
            campaign_id=self.campaign.campaign_id,
            delta=step.sut_delta.model_dump(by_alias=True),
            base_dir=PROJECT_ROOT,
            provider=self._infrastructure_provider,
        )
        directory = run_root / "sut_deltas"
        directory.mkdir(exist_ok=True)
        receipt = directory / f"{contract.occurrence:03d}.json"
        receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if result["errors"]:
            raise RuntimeReadinessError(
                "C0045 SUT delta application failed: " + "; ".join(result["errors"])
            )

    def _run_contracted_c0045(self) -> RuntimeCampaignReport:
        """Run the original ten-row ShadowRay inventory with typed evidence bounds."""
        run_root = self.output_dir / "runtime-v2" / self.run_id
        run_root.mkdir(parents=True, exist_ok=False)
        self.evidence_dir = run_root
        self._infrastructure_provider = detect_lab_infrastructure(self.sut.campaign_id)
        provisional = FactScope(
            run_id=self.run_id,
            environment_id=f"lab-{self.run_id}",
            epoch="not-probed",
            locus="target",
            host_id="target-linux-1",
            principal="rayuser",
        )
        contracts = load_c0045_full_runtime_contracts(provisional, registry)
        steps = [
            RuntimeCampaignStep(contract=contract, status="not_run", outcome=None)
            for contract in contracts
        ]
        retain_campaign_report(
            self._runtime_campaign_report(steps, None),
            run_root=run_root,
            filename="plan.json",
        )
        try:
            if not self._infrastructure_provider:
                raise RuntimeError("C0045 typed runtime requires a reachable guest")
            bootstrap = bootstrap_lab_authority(
                sut_profile_id="0.shadowray",
                expected_host_id="target-linux-1",
                principal="rayuser",
                run_id=self.run_id,
                environment_id=provisional.environment_id,
                run_root=run_root,
                store=self.fact_store,
            )
            contracts = load_c0045_full_runtime_contracts(bootstrap.scope, registry)
        except Exception as error:
            retain_campaign_report(
                self._runtime_campaign_report(steps, None, error),
                run_root=run_root,
                filename="summary.json",
            )
            raise
        for index, contract in enumerate(contracts):
            try:
                self._apply_c0045_step_delta(contract, run_root)
                if contract.mode == "real_controlled":
                    self._refresh_guest_authority(contract.scope, run_root)
                outcome = self.execute_contracted_occurrence(
                    contract,
                    self._c0045_observer_requests(contract),
                    run_root=run_root,
                    live_observer=self._c0045_live_observer(contract),
                )
                passed = outcome.invocation.executor_completed and (
                    contract.mode == "naive_simulated"
                    or bool(outcome.observations)
                    and all(item.passed for item in outcome.observations)
                )
                status = (
                    ("simulated" if contract.mode == "naive_simulated" else "observed")
                    if passed
                    else "failed"
                )
                steps[index] = RuntimeCampaignStep(
                    contract=contract,
                    status=status,
                    outcome=outcome,
                )
            except Exception as error:
                steps[index] = RuntimeCampaignStep(
                    contract=contract,
                    status="blocked"
                    if isinstance(error, RuntimeReadinessError)
                    else "error",
                    outcome=None,
                    error_type=type(error).__name__,
                    error_message=str(error),
                    process_failure=process_failure(error),
                )
        report = self._runtime_campaign_report(steps, bootstrap)
        retain_campaign_report(report, run_root=run_root, filename="summary.json")
        return report

    def run(self) -> CampaignEvidence | RuntimeCampaignReport:
        """Execute full campaign and return structured evidence."""
        if self.require_lab:
            require_live_campaign(self.campaign_id)
        if self.campaign_id == "0.c0026":
            return self._run_contracted_c0026()
        if self.campaign_id == "0.c0010":
            return self._run_contracted_c0010()
        if self.campaign_id == "0.costaricto":
            return self._run_contracted_costaricto()
        if self.campaign_id == "0.shadowray":
            return self._run_contracted_c0045()
        start_time = datetime.now()
        steps = self.campaign.steps
        total = len(steps)

        # Detect lab infrastructure before execution
        self._infrastructure_provider = detect_lab_infrastructure(self.sut.campaign_id)
        if self.require_lab and not self._infrastructure_provider:
            raise RuntimeError(
                "No reachable VM-backed lab was detected for "
                f"{self.sut.campaign_id}. Refusing to create campaign/SUT "
                "evidence from host-local execution."
            )

        print(f"\n{'=' * 70}")
        print(f"  CAMPAIGN: {self.campaign.name}")
        print(f"  ID: {self.campaign.campaign_id}")
        print(f"  SUT: {self.sut.campaign_id}")
        print(f"  Steps: {total}")
        print(f"  Objective: {self.campaign.objective}")
        if self._infrastructure_provider:
            print(f"  Infrastructure: {self._infrastructure_provider}")
        else:
            print("  Infrastructure: local (no lab VMs detected)")
        print(f"{'=' * 70}\n")

        # Pre-flight validation
        error = validate_campaign_sut_pair(self.campaign.campaign_id)
        if error:
            print(f"[WARN] Campaign/SUT validation: {error}")

        evidence = CampaignEvidence(
            campaign_id=self.campaign.campaign_id,
            sut_profile_id=self.sut.campaign_id,
            start_time=start_time,
            infrastructure_provider=self._infrastructure_provider,
            sut_profile_path=str(
                Path("data/sut_profiles") / f"{self.sut.campaign_id}.yml"
            ),
        )

        for i, step in enumerate(steps, start=1):
            if DEBUG_ENABLED:
                print(
                    "[STATE BEFORE]",
                    f"step: {step.technique_id}",
                    f"capabilities: {sorted(self.accumulated_capabilities)}",
                )
            print(f"[{i}/{total}] {step.technique_id} - {step.technique_name}")
            print(
                f"         mode={step.expected_mode.value}  fidelity={step.expected_fidelity.value}"
            )

            tech_evidence = self._execute_step(step)
            evidence.technique_results.append(tech_evidence)

            # Accumulate capabilities from successful executions
            if tech_evidence.status == "success":
                self.accumulated_capabilities.update(
                    tech_evidence.capabilities_produced
                )

            if DEBUG_ENABLED:
                print(
                    "[STATE AFTER]",
                    f"step: {step.technique_id}",
                    f"capabilities: {sorted(self.accumulated_capabilities)}",
                )

            status_icon = "OK" if tech_evidence.status == "success" else "FAIL"
            print(
                f"         [{status_icon}] declared_fidelity={tech_evidence.fidelity.declared.value}"
            )
            print()

        evidence.end_time = datetime.now()
        evidence.compute_summary()

        # Populate ACM-aligned artifact metadata
        import platform as plat

        duration_ms = int(
            (evidence.end_time - evidence.start_time).total_seconds() * 1000
        )
        limitations = []
        if evidence.fidelity_distribution.get("inspired", 0) > 0:
            limitations.append(
                f"{evidence.fidelity_distribution['inspired']} techniques classified "
                f"as INSPIRED due to platform mismatch or mechanism divergence"
            )
        if plat.machine() == "arm64":
            limitations.append(
                "Executed on ARM64 - QEMU provider may ignore private network config"
            )

        evidence.artifact_metadata = ArtifactMetadata(
            automation_level="zero-touch",
            reproducibility_notes=(
                f"Run: python3 scripts/run_campaign.py --campaign {self.campaign.campaign_id}. "
                f"Requires: Python 3.10+, pydantic. "
                f"Full lab mode additionally requires: Vagrant, QEMU/VirtualBox/libvirt."
            ),
            known_limitations=limitations,
            platform_requirements=f"{plat.system()} {plat.machine()}, Python {plat.python_version()}",
            estimated_duration_minutes=max(1, duration_ms // 60000),
            rubric_consistent=True,
        )

        self._save_evidence(evidence)
        self._print_summary(evidence)

        return evidence

    def _execute_step(self, step) -> TechniqueEvidence:
        """Execute a single campaign step and return TechniqueEvidence."""
        start_time = datetime.now()
        sut_adjustments_applied: list[str] = []
        sut_adjustment_errors: list[str] = []

        if step.sut_delta and self._infrastructure_provider:
            delta_result = apply_step_sut_delta(
                campaign_id=self.campaign.campaign_id,
                delta=step.sut_delta.model_dump(by_alias=True),
                base_dir=PROJECT_ROOT,
                provider=self._infrastructure_provider,
            )
            sut_adjustments_applied = delta_result["applied"]
            sut_adjustment_errors = delta_result["errors"]
            if delta_result["notes"]:
                print(f"         sut_delta={delta_result['notes']}")
            if DEBUG_ENABLED and sut_adjustments_applied:
                print(
                    "[SUT DELTA]",
                    f"step: {step.technique_id}",
                    f"applied: {sut_adjustments_applied}",
                )
            if sut_adjustment_errors:
                return self._make_skipped_evidence(
                    step,
                    start_time,
                    "SUT delta application failed: " + "; ".join(sut_adjustment_errors),
                    sut_adjustments_applied=sut_adjustments_applied,
                    sut_adjustment_errors=sut_adjustment_errors,
                )

        try:
            raw_evidence = execute_technique(
                technique_id=step.technique_id,
                available_capabilities=list(self.accumulated_capabilities),
                campaign_id=self.campaign.campaign_id,
                sut_profile_id=self.sut.campaign_id,
            )

            # Build FidelityAssessment from executor metadata + step expectation
            metadata = registry.get_metadata(
                step.technique_id, self.campaign.campaign_id
            )
            original_plat = (
                Platform.WINDOWS
                if metadata and metadata.original_platform == "windows"
                else Platform.ANY
            )
            exec_plat = Platform.LINUX

            fidelity = FidelityAssessment(
                declared=ExecutionFidelity(raw_evidence.execution_fidelity),
                justification=raw_evidence.fidelity_justification,
                platform_mismatch=(
                    original_plat != Platform.ANY and original_plat != exec_plat
                ),
                original_platform=original_plat,
                execution_platform=exec_plat,
            )

            host = self._infer_host(raw_evidence)

            return TechniqueEvidence(
                technique_id=step.technique_id,
                executor_name=raw_evidence.executor_name,
                technique_name=step.technique_name,
                status=raw_evidence.status,
                execution_mode=ExecutionMode(raw_evidence.execution_mode),
                fidelity=fidelity,
                artifacts=raw_evidence.artifacts_created,
                capabilities_consumed=raw_evidence.prerequisites_consumed,
                capabilities_produced=raw_evidence.capabilities_produced,
                stdout=raw_evidence.stdout[:2000],
                stderr=raw_evidence.stderr[:2000],
                start_time=start_time,
                end_time=datetime.now(),
                duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                host=host,
                sut_adjustments_applied=sut_adjustments_applied,
                sut_adjustment_errors=sut_adjustment_errors,
            )

        except Exception as e:
            return self._make_skipped_evidence(
                step,
                start_time,
                str(e),
                sut_adjustments_applied=sut_adjustments_applied,
                sut_adjustment_errors=sut_adjustment_errors,
            )

    def _infer_host(self, raw_evidence) -> str:
        """Legacy executor output does not attest the execution host."""
        return ""

    def _make_skipped_evidence(
        self,
        step,
        start_time,
        reason: str,
        sut_adjustments_applied: Optional[list[str]] = None,
        sut_adjustment_errors: Optional[list[str]] = None,
    ) -> TechniqueEvidence:
        """Create evidence for a skipped/failed step."""
        return TechniqueEvidence(
            technique_id=step.technique_id,
            technique_name=step.technique_name,
            status="failed",
            execution_mode=step.expected_mode,
            fidelity=FidelityAssessment(
                declared=step.expected_fidelity,
                justification=f"Execution failed: {reason}",
            ),
            stderr=reason,
            start_time=start_time,
            end_time=datetime.now(),
            sut_adjustments_applied=sut_adjustments_applied or [],
            sut_adjustment_errors=sut_adjustment_errors or [],
        )

    def _save_evidence(self, evidence: CampaignEvidence):
        """Save CampaignEvidence as JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        evidence_dir = self.output_dir / f"{evidence.campaign_id}_{timestamp}"
        evidence_dir.mkdir(exist_ok=True)

        def sanitize_text(value: str) -> str:
            project_root = str(PROJECT_ROOT)
            home_dir = str(HOME_DIR)
            sanitized = value.replace(project_root + os.sep, "")
            sanitized = sanitized.replace(project_root, ".")
            sanitized = sanitized.replace(home_dir + os.sep, "~/")
            sanitized = sanitized.replace(home_dir, "~")
            return sanitized

        def sanitize_payload(value: Any) -> Any:
            if isinstance(value, str):
                return sanitize_text(value)
            if isinstance(value, list):
                return [sanitize_payload(item) for item in value]
            if isinstance(value, dict):
                return {key: sanitize_payload(item) for key, item in value.items()}
            return value

        # Summary (full Pydantic model serialized)
        summary_path = evidence_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(
                sanitize_payload(evidence.model_dump(mode="json")),
                f,
                indent=2,
                ensure_ascii=False,
            )

        # Compact manifest for quick inspection
        manifest = {
            "campaign_id": evidence.campaign_id,
            "sut_profile_id": evidence.sut_profile_id,
            "timestamp": timestamp,
            "total_techniques": evidence.total_techniques,
            "successful": evidence.successful,
            "failed": evidence.failed,
            "skipped": evidence.skipped,
            "fidelity_distribution": evidence.fidelity_distribution,
            "evidence_directory": sanitize_text(str(evidence_dir)),
        }
        with open(evidence_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        # Per-technique detail files
        per_tech_dir = evidence_dir / "per_technique"
        per_tech_dir.mkdir(exist_ok=True)
        for te in evidence.technique_results:
            tech_file = per_tech_dir / f"{te.technique_id}.json"
            with open(tech_file, "w", encoding="utf-8") as f:
                json.dump(
                    sanitize_payload(te.model_dump(mode="json")),
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

        print(f"\n[EVIDENCE] Saved to: {evidence_dir}")
        self.evidence_dir = evidence_dir

    def _print_summary(self, evidence: CampaignEvidence):
        """Print human-readable summary."""
        print(f"\n{'=' * 70}")
        print(f"  EXECUTION COMPLETE: {evidence.campaign_id}")
        print(f"{'=' * 70}")
        print(f"  Total:      {evidence.total_techniques}")
        print(f"  Successful: {evidence.successful}")
        print(f"  Failed:     {evidence.failed}")
        print(f"  Declared fidelity: {evidence.fidelity_distribution}")
        print()

        for te in evidence.technique_results:
            icon = "OK  " if te.status == "success" else "FAIL"
            print(
                f"  [{icon}] {te.technique_id:12s} "
                f"{te.fidelity.declared.value:10s} "
                f"{te.technique_name}"
            )

        print(f"{'=' * 70}\n")


def main():
    from runners.caldera_session import campaign_caldera_session

    parser = argparse.ArgumentParser(
        description="STICKS Unified Campaign Runner (formal model)",
    )
    parser.add_argument(
        "--campaign",
        help="Campaign ID (e.g., 0.c0011). Omit to list available.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Execute ALL available campaigns sequentially",
    )
    parser.add_argument(
        "--output",
        default="runs/evidence",
        help="Output evidence directory",
    )
    parser.add_argument(
        "--require-lab",
        action="store_true",
        help=(
            "Require a reachable VM-backed lab. Use this for campaign/SUT "
            "evidence; host-local execution remains limited to development tests."
        ),
    )

    parser.add_argument("--caldera-session", type=Path,
                        help="Prepared isolated CALDERA session; API key comes from environment")
    args = parser.parse_args()
    if args.caldera_session and (not args.require_lab or args.all or args.campaign not in SUPPORTED_CALDERA_CAMPAIGNS):
        parser.error("CALDERA session requires --require-lab and a reviewed C0010 or C0026 campaign")

    # List mode
    if not args.campaign and not args.all:
        print("Available campaigns:")
        for cid in list_campaigns():
            print(f"  - {cid}")
        return 0

    # Determine which campaigns to run
    campaign_ids = list_campaigns() if args.all else [args.campaign]

    exit_code = 0
    for cid in campaign_ids:
        try:
            runner = UnifiedCampaignRunner(
                campaign_id=cid,
                output_dir=args.output,
                require_lab=args.require_lab,
            )
            dispatch_context = (
                campaign_caldera_session(
                    args.caldera_session, Path(args.output) / "caldera-dispatch"
                ) if args.caldera_session else nullcontext()
            )
            with dispatch_context:
                evidence = runner.run()
            if evidence.failed > 0:
                exit_code = 1
        except FileNotFoundError as e:
            print(f"\n[ERROR] {e}")
            exit_code = 1
        except Exception as e:
            print(f"\n[ERROR] Campaign {cid} failed: {e}")
            traceback.print_exc()
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
