"""Validate retained typed runtime evidence without invoking guest code."""

import hashlib
import os
from uuid import UUID
from pathlib import Path

from runners.c0026_runtime_contracts import C0026ContractPopulation
from runners.c0010_runtime_contracts import C0010ContractPopulation
from runners.c0045_full_runtime_contracts import C0045ContractPopulation
from runners.costaricto_runtime_contracts import CostaRictoContractPopulation
from runners.capability_authority import verify_registered_observation
from runners.capability_facts import CapabilityFact, FactScope, ObservationReference
from runners.capability_observations import (
    _directory,
    _read_record,
    verify_observation_reference,
)
from runners.runtime_campaign_report import RuntimeCampaignReport
from runners.runtime_journal import RuntimeJournalRecord
from evaluation.controlled_comparison import ExecutionSemanticBridge

_SOURCE_PATHS = {
    "executors.executor_registry": "src/executors/executor_registry.py",
    "executors.legacy_parity_expansion_executors": "src/executors/legacy_parity_expansion_executors.py",
}
_CONTRACT_PATH = "data/runtime_contracts/c0026.json"
_C0010_CONTRACT_PATH = "data/runtime_contracts/c0010.json"
_C0010_SOURCE_PATHS = {
    "executors.executor_registry": "src/executors/executor_registry.py",
    "executors.legacy_campaign_executors": "src/executors/legacy_campaign_executors.py",
}
_C0010_OBSERVER_PATHS = (
    "data/observer_specs/c0010_controller.json",
    "src/runners/c0010_controller_observers.py",
    "src/runners/c0010_http_observer.py",
    "src/runners/c0010_guest_observer.py",
    "scripts/probe_c0010_controller.py",
    "scripts/probe_c0010_http.py",
    "scripts/probe_c0010_target.py",
)
_C0010_PROBE_BY_AUTHORITY = {
    "c0010-payload": "scripts/probe_c0010_controller.py",
    "c0010-page": "scripts/probe_c0010_controller.py",
    "c0010-http": "scripts/probe_c0010_http.py",
    "c0010-tool": "scripts/probe_c0010_controller.py",
    "c0010-transfer": "scripts/probe_c0010_target.py",
}
_COSTARICTO_CONTRACT_PATH = "data/runtime_contracts/costaricto.json"
_COSTARICTO_PROBE_PATH = "scripts/probe_costaricto_effects.py"
_COSTARICTO_SOURCE_PATHS = {
    "executors.executor_registry": "src/executors/executor_registry.py",
    "executors.fox_kitten_real": "src/executors/fox_kitten_real.py",
    "executors.legacy_parity_expansion_executors": "src/executors/legacy_parity_expansion_executors.py",
}
_COSTARICTO_OBSERVER_PATHS = (
    "src/runners/costaricto_capability_observers.py",
    "src/runners/capability_authority.py",
    "src/runners/costaricto_runtime_contracts.py",
    _COSTARICTO_PROBE_PATH,
)
_C0045_CONTRACT_PATH = "data/runtime_contracts/c0045.json"
_C0045_SOURCE_PATHS = {
    "executors.shadowray_fixed_executors": "src/executors/shadowray_fixed_executors.py",
    "executors.privilege_escalation_executors": (
        "src/executors/privilege_escalation_executors.py"
    ),
}
# The retained report is a certificate only relative to this semantic closure.
# Keep every source that can change C0045 observation acquisition, interpretation,
# registration, or replay in one explicit, reviewable set.
_C0045_EVIDENCE_SOURCE_PATHS = (
    "src/executors/c0045_readonly_commands.py",
    "src/executors/c0045_trace_executor.py",
    "src/executors/lab_transport.py",
    "src/runners/c0045_fixture_observer.py",
    "src/runners/c0045_full_runtime_contracts.py",
    "src/runners/c0045_trace_observer.py",
    "src/runners/capability_authority.py",
    "src/runners/capability_facts.py",
    "src/runners/capability_observations.py",
    "src/runners/campaign_runner.py",
    "src/runners/guest_execution_trace.py",
    "src/runners/lab_bootstrap_observer.py",
    "src/runners/runtime_campaign_report.py",
    "src/runners/runtime_invocation.py",
    "src/runners/runtime_journal.py",
    "src/runners/runtime_step_contracts.py",
    "scripts/probe_c0045_api.py",
    "scripts/probe_shadowray_target.py",
)
_C0045_PROBE_BY_AUTHORITY = {
    "c0045-api": "scripts/probe_c0045_api.py",
    "c0045-toolkit": "scripts/probe_shadowray_target.py",
    "c0045-transfer": "scripts/probe_shadowray_target.py",
    "c0045-python": "scripts/probe_shadowray_target.py",
    "c0045-network": "scripts/probe_shadowray_target.py",
}


def _read_relative(root: Path, relative: str) -> bytes:
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts) or "\\" in relative:
        raise ValueError("Evidence paths must be canonical and relative")
    with _directory(None, str(root)) as directory:
        return _read_nested(directory, parts)


def _read_nested(directory: int, parts: list[str]) -> bytes:
    if len(parts) == 1:
        return _read_record(directory, parts[0])
    with _directory(directory, parts[0]) as child:
        return _read_nested(child, parts[1:])


def _bound_population(workspace: Path, manifest: dict) -> C0026ContractPopulation:
    paths = (_CONTRACT_PATH, *_SOURCE_PATHS.values())
    digests = {}
    for path in paths:
        entries = [entry for entry in manifest["files"] if entry["path"] == path]
        if len(entries) != 1:
            raise ValueError("Seal requires exactly one manifest binding per source")
        content = _read_relative(workspace, path)
        digest = hashlib.sha256(content).hexdigest()
        if digest != entries[0]["sha256"]:
            raise ValueError("Workspace source differs from its retained manifest")
        digests[path] = digest
    population = C0026ContractPopulation.model_validate_json(
        _read_relative(workspace, _CONTRACT_PATH)
    )
    if [row.occurrence for row in population.occurrences] != list(range(1, 7)):
        raise ValueError("C0026 seal requires all six ordered occurrences")
    for row in population.occurrences:
        module = row.executor_id.rsplit(".", 1)[0]
        if (
            module not in _SOURCE_PATHS
            or row.executor_sha256 != digests[_SOURCE_PATHS[module]]
        ):
            raise ValueError("Executor contract differs from its sealed source")
    return population


def _bound_c0010_population(workspace: Path, manifest: dict) -> C0010ContractPopulation:
    paths = (
        _C0010_CONTRACT_PATH,
        *_C0010_SOURCE_PATHS.values(),
        *_C0010_OBSERVER_PATHS,
    )
    digests = {}
    for path in paths:
        entries = [entry for entry in manifest["files"] if entry["path"] == path]
        if len(entries) != 1:
            raise ValueError("C0010 seal requires one manifest binding per source")
        digest = hashlib.sha256(_read_relative(workspace, path)).hexdigest()
        if digest != entries[0]["sha256"]:
            raise ValueError(
                "C0010 runtime or observer differs from the source manifest"
            )
        digests[path] = digest
    population = C0010ContractPopulation.model_validate_json(
        _read_relative(workspace, _C0010_CONTRACT_PATH)
    )
    if [row.occurrence for row in population.occurrences] != list(range(1, 10)):
        raise ValueError("C0010 seal requires all nine ordered occurrences")
    for row in population.occurrences:
        module = row.executor_id.rsplit(".", 1)[0]
        if (
            module not in _C0010_SOURCE_PATHS
            or row.executor_sha256 != digests[_C0010_SOURCE_PATHS[module]]
        ):
            raise ValueError("C0010 executor differs from its sealed source")
    return population


def _bound_costaricto_population(
    workspace: Path, manifest: dict
) -> CostaRictoContractPopulation:
    paths = (
        _COSTARICTO_CONTRACT_PATH,
        "campaigns/0.costaricto.json",
        "data/sut_profiles/0.costaricto.yml",
        *_COSTARICTO_SOURCE_PATHS.values(),
        *_COSTARICTO_OBSERVER_PATHS,
    )
    digests = {}
    for path in paths:
        entries = [entry for entry in manifest["files"] if entry["path"] == path]
        if len(entries) != 1:
            raise ValueError("CostaRicto seal requires one binding per source")
        digest = hashlib.sha256(_read_relative(workspace, path)).hexdigest()
        if digest != entries[0]["sha256"]:
            raise ValueError("CostaRicto source differs from its retained manifest")
        digests[path] = digest
    population = CostaRictoContractPopulation.model_validate_json(
        _read_relative(workspace, _COSTARICTO_CONTRACT_PATH)
    )
    if [row.occurrence for row in population.occurrences] != list(range(1, 11)):
        raise ValueError("CostaRicto seal requires all ten ordered occurrences")
    for row in population.occurrences:
        module = row.executor_id.rsplit(".", 1)[0]
        if (
            module not in _COSTARICTO_SOURCE_PATHS
            or row.executor_sha256 != digests[_COSTARICTO_SOURCE_PATHS[module]]
        ):
            raise ValueError("CostaRicto executor differs from its sealed source")
    return population


def _bound_c0045_population(workspace: Path, manifest: dict) -> C0045ContractPopulation:
    """Load the full C0045 contract after binding every executor source."""
    paths = (
        _C0045_CONTRACT_PATH,
        *_C0045_SOURCE_PATHS.values(),
        *_C0045_EVIDENCE_SOURCE_PATHS,
    )
    digests = {}
    for path in paths:
        entries = [entry for entry in manifest["files"] if entry["path"] == path]
        if len(entries) != 1:
            raise ValueError("C0045 seal requires one binding per source")
        digest = hashlib.sha256(_read_relative(workspace, path)).hexdigest()
        if digest != entries[0]["sha256"]:
            raise ValueError(
                "C0045 runtime or observer differs from the source manifest"
            )
        digests[path] = digest
    population = C0045ContractPopulation.model_validate_json(
        _read_relative(workspace, _C0045_CONTRACT_PATH)
    )
    occurrences = list(range(1, 11))
    if [row.occurrence for row in population.occurrences] != occurrences:
        raise ValueError("C0045 seal requires all ten ordered occurrences")
    if sorted(row.plan_sequence for row in population.occurrences) != occurrences:
        raise ValueError("C0045 seal requires a causal permutation of every plan step")
    for row in population.occurrences:
        module = row.executor_id.rsplit(".", 1)[0]
        if (
            module not in _C0045_SOURCE_PATHS
            or row.executor_sha256 != digests[_C0045_SOURCE_PATHS[module]]
        ):
            raise ValueError("C0045 executor differs from its sealed source")
    return population


def _parse_report(payload: dict) -> RuntimeCampaignReport:
    counters = RuntimeCampaignReport.model_computed_fields
    report = RuntimeCampaignReport.model_validate(
        {key: value for key, value in payload.items() if key not in counters}
    )
    for name in counters:
        if type(payload.get(name)) is not int or payload[name] != getattr(report, name):
            raise ValueError("Reported aggregate differs from retained step outcomes")
    if report.failed or report.error_type or report.error_message:
        raise ValueError(
            "Incomplete or failed campaigns cannot receive a completion seal"
        )
    return report


def _verify_reference(reference: ObservationReference, root: Path, scope: FactScope):
    observed = verify_registered_observation(
        reference,
        run_root=root,
        expected_scope=scope,
        expected_predicate=reference.predicate_id,
    )
    if not observed.passed:
        raise ValueError("Completion requires passing registered acquisitions")
    return observed


def _verify_fact(fact: CapabilityFact, root: Path) -> None:
    observed = _verify_reference(fact.observation, root, fact.scope)
    if (
        fact.name not in observed.established_facts
        or fact.producer_occurrence != observed.producer_occurrence
        or fact.content_sha256 != observed.content_sha256
    ):
        raise ValueError("Granted fact differs from the retained acquisition")


def _verify_bootstrap(
    report: RuntimeCampaignReport, root: Path, principal: str = "ubuntu"
) -> FactScope:
    bootstrap = report.bootstrap
    if bootstrap is None:
        raise ValueError("Completion requires retained lab lifecycle identity")
    scope = bootstrap.scope
    if (
        scope.run_id != report.run_id
        or scope.locus != "target"
        or scope.host_id != "target-linux-1"
        or scope.principal != principal
    ):
        raise ValueError("Bootstrap does not identify the selected run and target")
    discovered = verify_observation_reference(
        bootstrap.discovery_reference,
        run_root=root,
        expected_scope=scope,
        expected_predicate="lifecycle-identity",
    )
    if (
        bootstrap.discovery_reference.authority_id != "lab-lifecycle"
        or not discovered.passed
    ):
        raise ValueError("Lifecycle discovery is missing or unsuccessful")
    measured = _verify_reference(bootstrap.reference, root, scope)
    if (
        bootstrap.reference.authority_id != "lab-shell"
        or measured.predicate_id != "shell-nonce"
    ):
        raise ValueError("Bootstrap requires the registered shell authority")
    if len(bootstrap.facts) != 1 or bootstrap.facts[0].name != "lab:shell":
        raise ValueError("Bootstrap must grant only the measured lab shell")
    for fact in bootstrap.facts:
        if fact.observation != bootstrap.reference:
            raise ValueError("Bootstrap fact refers to a different acquisition")
        _verify_fact(fact, root)
    return scope


def _verify_contract(step, row, report, guest_scope):
    contract = step.contract
    expected_scope = (
        guest_scope
        if row.mode == "real_controlled"
        else FactScope(
            run_id=report.run_id,
            environment_id=guest_scope.environment_id,
            epoch=report.run_id,
            locus="controller",
            host_id="controller",
            principal=None,
        )
    )
    for name in (
        "occurrence",
        "technique_id",
        "executor_id",
        "executor_sha256",
        "mode",
        "observers",
    ):
        if getattr(contract, name) != getattr(row, name):
            raise ValueError("Reported occurrence differs from the sealed contract")
    if contract.campaign_id != report.campaign_id or contract.scope != expected_scope:
        raise ValueError("Occurrence has a different campaign or lifecycle scope")
    if tuple(item.name for item in contract.requirements) != row.requirements:
        raise ValueError("Occurrence prerequisites differ from the sealed contract")
    if any(item.scope != guest_scope for item in contract.requirements):
        raise ValueError("Occurrence prerequisite refers to a different guest")


def _verify_step(step, root: Path, produced: dict) -> None:
    outcome, contract = step.outcome, step.contract
    if outcome.invocation.executor_id != contract.executor_id:
        raise ValueError("Invocation differs from the selected executor")
    if (
        tuple(ref.authority_id for ref in outcome.observation_references)
        != contract.observers
    ):
        raise ValueError("Occurrence observations differ from its declared authorities")
    if len(outcome.observations) != len(outcome.observation_references):
        raise ValueError("Every observation must identify its retained acquisition")
    grants = []
    for reference, reported in zip(
        outcome.observation_references, outcome.observations
    ):
        measured = _verify_reference(reference, root, contract.scope)
        if measured != reported or measured.producer_occurrence != contract.occurrence:
            raise ValueError("Effect differs from its measured producing occurrence")
        grants.extend(
            CapabilityFact(
                name=name,
                origin="observed",
                scope=measured.scope,
                producer_occurrence=measured.producer_occurrence,
                observation=reference,
                content_sha256=measured.content_sha256,
            )
            for name in measured.established_facts
        )
    if tuple(grants) != outcome.authorizing_facts:
        raise ValueError("Authorizing products differ from the measured products")
    if len(outcome.consumed_references) != len(contract.requirements):
        raise ValueError("Every prerequisite requires its consumed observation")
    mutable_inputs = []
    for requirement, reference in zip(
        contract.requirements, outcome.consumed_references
    ):
        measured = _verify_reference(reference, root, requirement.scope)
        if requirement.name not in measured.established_facts:
            raise ValueError("Consumed observation does not establish its prerequisite")
        if requirement.name != "lab:shell":
            prior = produced.get(reference)
            if (
                prior is None
                or prior.name != requirement.name
                or prior.producer_occurrence >= contract.occurrence
            ):
                raise ValueError(
                    "Product prerequisite has no earlier observed producer"
                )
            mutable_inputs.append(prior)
    live_controller_fetch = (
        contract.campaign_id == "0.c0010"
        and contract.occurrence == 4
        and len(mutable_inputs) == 1
        and len(outcome.observation_references) == 1
        and len(outcome.observations) == 1
        and outcome.observation_references[0].authority_id == "c0010-http"
        and outcome.observations[0].predicate_id == "loopback-http-fetch"
    )
    if live_controller_fetch:
        mutable_inputs.clear()
    if len(step.revalidation_references) != len(mutable_inputs):
        raise ValueError("Mutable inputs require retained fresh revalidations")
    for prior, reference in zip(mutable_inputs, step.revalidation_references):
        if reference == prior.observation:
            raise ValueError("Mutable input requires a fresh acquisition, not a replay")
        fresh = _verify_reference(reference, root, prior.scope)
        if (
            fresh.content_sha256 is None
            or fresh.content_sha256 != prior.content_sha256
            or fresh.producer_occurrence != prior.producer_occurrence
            or fresh.consumer_occurrence != contract.occurrence
            or fresh.revalidated_reference != prior.observation
            or prior.name not in fresh.established_facts
        ):
            raise ValueError("Product changed before its dependent occurrence")
        if any(
            item.details.get("nss_input_sha256") != prior.content_sha256
            for item in outcome.observations
        ):
            raise ValueError("Measured output did not consume the acquired input bytes")
    for fact in outcome.authorizing_facts:
        produced[fact.observation] = fact
    for fact in outcome.simulated_facts:
        if fact.producer_occurrence != contract.occurrence:
            raise ValueError("Simulated product differs from its producing occurrence")


def _verify_journal(report: RuntimeCampaignReport, root: Path) -> None:
    listed = [reference.record_path for reference in report.journal_references]
    with _directory(None, str(root)) as directory:
        with _directory(directory, "runtime_journal") as journal:
            actual = {f"runtime_journal/{name}" for name in os.listdir(journal)}
    if len(set(listed)) != len(listed) or set(listed) != actual:
        raise ValueError(
            "Journal inventory differs from the complete retained checkpoints"
        )
    records = []
    for reference in report.journal_references:
        parts = reference.record_path.split("/")
        if len(parts) != 2 or parts[0] != "runtime_journal":
            raise ValueError("Journal reference must identify a retained checkpoint")
        content = _read_relative(root, reference.record_path)
        if hashlib.sha256(content).hexdigest() != reference.record_sha256:
            raise ValueError("Journal digest differs from retained bytes")
        records.append(RuntimeJournalRecord.model_validate_json(content))
    for step in report.steps:
        checkpoints = [
            item
            for item in records
            if item.contract.occurrence == step.contract.occurrence
        ]
        if [item.phase for item in checkpoints] != [
            "started",
            "executor_completed",
            step.status,
        ]:
            raise ValueError("Occurrence lacks its ordered completion checkpoints")
        if any(item.contract != step.contract for item in checkpoints):
            raise ValueError("Journal checkpoint has a different occurrence contract")
        terminal = checkpoints[-1]
        outcome = step.outcome
        for checkpoint in checkpoints:
            if (
                checkpoint.consumed_references != outcome.consumed_references
                or checkpoint.revalidation_references != step.revalidation_references
            ):
                raise ValueError("Journal prerequisites changed within an occurrence")
        if checkpoints[1].invocation != outcome.invocation:
            raise ValueError(
                "Original executor return differs from the terminal outcome"
            )
        if any(
            first.recorded_at > second.recorded_at
            for first, second in zip(checkpoints, checkpoints[1:])
        ):
            raise ValueError("Journal checkpoints have inconsistent temporal ordering")
        if (
            terminal.invocation != outcome.invocation
            or terminal.observation_references != outcome.observation_references
            or terminal.authorizing_facts != outcome.authorizing_facts
            or terminal.simulated_facts != outcome.simulated_facts
            or terminal.consumed_references != outcome.consumed_references
            or terminal.revalidation_references != step.revalidation_references
        ):
            raise ValueError("Journal terminal differs from the campaign outcome")
    if any(
        item.contract not in [step.contract for step in report.steps]
        for item in records
    ):
        raise ValueError(
            "Journal contains an occurrence outside the selected population"
        )


def validate_typed_completion(
    payload: dict, evidence: Path, workspace: Path, manifest: dict
) -> RuntimeCampaignReport:
    """Validate consistency of trusted-controller records, not current guest effects."""
    population = _bound_population(workspace, manifest)
    report = _parse_report(payload)
    identity = UUID(report.run_id)
    if identity.hex != report.run_id or identity.version != 4:
        raise ValueError("Typed run identity must be a canonical UUID4 hex value")
    if report.campaign_id != population.campaign_id or len(report.steps) != 6:
        raise ValueError("Seal requires the complete selected C0026 population")
    scope = _verify_bootstrap(report, evidence)
    produced = {}
    for step, row in zip(report.steps, population.occurrences):
        _verify_contract(step, row, report, scope)
        _verify_step(step, evidence, produced)
    for fact in report.runtime_facts:
        if fact.scope.run_id != report.run_id:
            raise ValueError("Runtime fact belongs to a different run")
        if fact.origin == "observed":
            _verify_fact(fact, evidence)
    _verify_journal(report, evidence)
    return report


def _verify_c0010_contract(step, row, report, guest_scope):
    contract = step.contract
    if row.locus == "target":
        expected_scope = guest_scope
    else:
        expected_scope = contract.scope
        if (
            expected_scope.run_id != report.run_id
            or expected_scope.environment_id != guest_scope.environment_id
            or expected_scope.epoch != report.run_id
            or expected_scope.locus != "controller"
            or expected_scope.host_id != "controller"
            or not expected_scope.principal
            or not expected_scope.principal.isdigit()
        ):
            raise ValueError("C0010 controller scope differs from the run")
    if row.locus != ("target" if row.occurrence == 9 else "controller"):
        raise ValueError("C0010 target authority moved to a different occurrence")
    for name in (
        "occurrence",
        "technique_id",
        "executor_id",
        "executor_sha256",
        "mode",
        "observers",
    ):
        if getattr(contract, name) != getattr(row, name):
            raise ValueError("C0010 occurrence differs from its sealed contract")
    if contract.campaign_id != report.campaign_id or contract.scope != expected_scope:
        raise ValueError("C0010 occurrence has a different campaign or scope")
    if tuple(item.name for item in contract.requirements) != row.requirements:
        raise ValueError("C0010 prerequisites differ from the sealed contract")
    for requirement in contract.requirements:
        required_scope = (
            guest_scope if requirement.name == "lab:shell" else contract.scope
        )
        if (
            requirement.scope != required_scope
            or requirement.accepted_origins != frozenset({"observed"})
        ):
            raise ValueError("C0010 prerequisite has an untrusted origin or scope")


def _verify_c0010_probe_sources(report: RuntimeCampaignReport, workspace: Path) -> None:
    probe_digests = {
        authority: hashlib.sha256(_read_relative(workspace, path)).hexdigest()
        for authority, path in _C0010_PROBE_BY_AUTHORITY.items()
    }
    specification_digest = hashlib.sha256(
        _read_relative(workspace, "data/observer_specs/c0010_controller.json")
    ).hexdigest()
    for step in report.steps:
        for reference, observation in zip(
            step.outcome.observation_references,
            step.outcome.observations,
            strict=True,
        ):
            if (
                observation.details.get("returncode") != 0
                or observation.details.get("probe_sha256")
                != probe_digests[reference.authority_id]
            ):
                raise ValueError("C0010 observation is not bound to the sealed probe")
            if reference.authority_id in {"c0010-payload", "c0010-page", "c0010-tool"}:
                if observation.details.get("spec_sha256") != specification_digest:
                    raise ValueError(
                        "C0010 controller observation used another specification"
                    )
            if reference.authority_id == "c0010-http" and (
                observation.details.get("failed_checks") != ""
                or observation.details.get("response_count") != 2
            ):
                raise ValueError("C0010 live HTTP observation is incomplete")
            if reference.authority_id == "c0010-transfer" and (
                observation.details.get("identity_matched") is not True
                or observation.content_sha256
                != "b088ddaef2625e7f19f1ef1031b8af0617d4e849134d367bde139c77b7ad7be9"
            ):
                raise ValueError(
                    "C0010 guest transfer is not the bounded benign payload"
                )


def validate_c0010_typed_completion(
    payload: dict, evidence: Path, workspace: Path, manifest: dict
) -> RuntimeCampaignReport:
    """Seal C0010's four controller effects and one bounded guest effect."""
    population = _bound_c0010_population(workspace, manifest)
    report = _parse_report(payload)
    identity = UUID(report.run_id)
    if identity.hex != report.run_id or identity.version != 4:
        raise ValueError("C0010 run identity must be a canonical UUID4 hex value")
    if report.campaign_id != population.campaign_id or len(report.steps) != 9:
        raise ValueError("C0010 seal requires the complete selected population")
    guest_scope = _verify_bootstrap(report, evidence)
    produced = {}
    for step, row in zip(report.steps, population.occurrences, strict=True):
        _verify_c0010_contract(step, row, report, guest_scope)
        expected_status = "simulated" if row.mode == "naive_simulated" else "observed"
        if step.status != expected_status:
            raise ValueError("C0010 occurrence status differs from its declared mode")
        _verify_step(step, evidence, produced)
    for fact in report.runtime_facts:
        if fact.scope.run_id != report.run_id:
            raise ValueError("C0010 runtime fact belongs to a different run")
        if fact.origin == "observed":
            _verify_fact(fact, evidence)
    _verify_c0010_probe_sources(report, workspace)
    _verify_journal(report, evidence)
    return report


def validate_costaricto_typed_completion(
    payload: dict, evidence: Path, workspace: Path, manifest: dict
) -> RuntimeCampaignReport:
    """Seal only three bounded guest effects and seven explicit simulations."""
    population = _bound_costaricto_population(workspace, manifest)
    report = _parse_report(payload)
    identity = UUID(report.run_id)
    if identity.hex != report.run_id or identity.version != 4:
        raise ValueError("CostaRicto run identity must be a canonical UUID4 hex")
    if report.campaign_id != population.campaign_id or len(report.steps) != 10:
        raise ValueError("CostaRicto seal requires all ten selected occurrences")
    guest_scope = _verify_bootstrap(report, evidence, principal="reconuser")
    probe_digest = hashlib.sha256(
        _read_relative(workspace, _COSTARICTO_PROBE_PATH)
    ).hexdigest()
    expected_digests = {
        "benign-transfer": "b088ddaef2625e7f19f1ef1031b8af0617d4e849134d367bde139c77b7ad7be9",
        "local-collection": "1a4b8e263ff8d5f4c16eb3a661e1e33ac2d6b40abc5d221ad44403c6b7fd6baa",
    }
    produced = {}
    for step, row in zip(report.steps, population.occurrences, strict=True):
        _verify_contract(step, row, report, guest_scope)
        expected_status = "simulated" if row.mode == "naive_simulated" else "observed"
        if step.status != expected_status:
            raise ValueError("CostaRicto status differs from its selected mode")
        _verify_step(step, evidence, produced)
        for observation in step.outcome.observations:
            if (
                observation.details.get("returncode") != 0
                or observation.details.get("predicate_source_sha256") != probe_digest
                or observation.details.get("passed") is not True
                or observation.details.get("input_sha256") != observation.content_sha256
                or observation.content_sha256 is None
            ):
                raise ValueError("CostaRicto effect lacks its bounded guest probe")
            expected_digest = expected_digests.get(observation.predicate_id)
            if expected_digest and observation.content_sha256 != expected_digest:
                raise ValueError("CostaRicto fixture bytes differ from the contract")
    for fact in report.runtime_facts:
        if fact.scope.run_id != report.run_id:
            raise ValueError("CostaRicto fact belongs to another run")
        if fact.origin == "observed":
            _verify_fact(fact, evidence)
    _verify_journal(report, evidence)
    if (report.effects_observed, report.simulated, report.failed) != (3, 7, 0):
        raise ValueError("CostaRicto counts differ from the reviewed scope")
    return report


def _verify_c0045_bridge(
    bridge: ExecutionSemanticBridge,
    population: C0045ContractPopulation,
    report: RuntimeCampaignReport,
) -> None:
    """Bind each runtime occurrence to the causal step it consumed."""
    if not bridge.validate_hash():
        raise ValueError("C0045 execution bridge content hash mismatch")
    if bridge.runtime_campaign_id != report.campaign_id:
        raise ValueError("C0045 bridge identifies a different runtime campaign")
    if len(bridge.steps) != len(population.occurrences):
        raise ValueError("C0045 bridge does not cover every runtime occurrence")
    for bridge_step, row, runtime_step in zip(
        bridge.steps, population.occurrences, report.steps, strict=True
    ):
        if (
            bridge_step.occurrence != row.occurrence
            or bridge_step.step_id != f"s{row.plan_sequence}"
            or bridge_step.technique_id != row.technique_id
            or bridge_step.executor_id != row.executor_id
            or bridge_step.executor_sha256 != row.executor_sha256
        ):
            raise ValueError("C0045 bridge differs from the sealed causal contract")
        if (
            runtime_step.contract.occurrence != bridge_step.occurrence
            or runtime_step.contract.technique_id != bridge_step.technique_id
            or runtime_step.contract.executor_id != bridge_step.executor_id
            or runtime_step.contract.executor_sha256 != bridge_step.executor_sha256
        ):
            raise ValueError("C0045 runtime report differs from its semantic bridge")


def _verify_c0045_contract(step, row, report, guest_scope) -> None:
    """Require C0045 to retain the guest scope for observed and simulated rows."""
    contract = step.contract
    for name in (
        "occurrence",
        "technique_id",
        "executor_id",
        "executor_sha256",
        "mode",
        "observers",
    ):
        if getattr(contract, name) != getattr(row, name):
            raise ValueError("C0045 occurrence differs from the sealed contract")
    if contract.campaign_id != report.campaign_id or contract.scope != guest_scope:
        raise ValueError("C0045 occurrence has a different campaign or guest scope")
    if tuple(item.name for item in contract.requirements) != row.requirements:
        raise ValueError(
            "C0045 occurrence prerequisites differ from the sealed contract"
        )
    for requirement in contract.requirements:
        if (
            requirement.scope != guest_scope
            or requirement.accepted_origins != frozenset({"observed"})
        ):
            raise ValueError("C0045 prerequisite has an untrusted origin or scope")


def _verify_c0045_probe_sources(report: RuntimeCampaignReport, workspace: Path) -> None:
    """Require every retained C0045 effect to identify its sealed probe bytes."""
    probe_digests = {
        authority: hashlib.sha256(_read_relative(workspace, path)).hexdigest()
        for authority, path in _C0045_PROBE_BY_AUTHORITY.items()
    }
    for step in report.steps:
        outcome = step.outcome
        if outcome is None:
            continue
        for reference, observation in zip(
            outcome.observation_references, outcome.observations, strict=True
        ):
            expected_digest = probe_digests.get(reference.authority_id)
            if expected_digest is None:
                raise ValueError(
                    "C0045 runtime used an undeclared observation authority"
                )
            if (
                observation.details.get("probe_sha256") != expected_digest
                or observation.details.get("identity_matched") is not True
            ):
                raise ValueError("C0045 observation is not bound to the sealed probe")


def validate_c0045_typed_completion(
    payload: dict,
    evidence: Path,
    workspace: Path,
    manifest: dict,
    bridge: ExecutionSemanticBridge,
) -> RuntimeCampaignReport:
    """Seal C0045's five observed effects and five explicit simulations."""
    population = _bound_c0045_population(workspace, manifest)
    report = _parse_report(payload)
    identity = UUID(report.run_id)
    if identity.hex != report.run_id or identity.version != 4:
        raise ValueError("C0045 run identity must be a canonical UUID4 hex value")
    if report.campaign_id != population.campaign_id or len(report.steps) != 10:
        raise ValueError("C0045 seal requires the complete selected population")
    guest_scope = _verify_bootstrap(report, evidence, principal="rayuser")
    _verify_c0045_bridge(bridge, population, report)
    produced = {}
    for step, row in zip(report.steps, population.occurrences, strict=True):
        _verify_c0045_contract(step, row, report, guest_scope)
        expected_status = "simulated" if row.mode == "naive_simulated" else "observed"
        if step.status != expected_status:
            raise ValueError("C0045 occurrence status differs from its selected mode")
        _verify_step(step, evidence, produced)
    for fact in report.runtime_facts:
        if fact.scope.run_id != report.run_id:
            raise ValueError("C0045 runtime fact belongs to another run")
        if fact.origin == "observed":
            _verify_fact(fact, evidence)
    _verify_c0045_probe_sources(report, workspace)
    _verify_journal(report, evidence)
    if (report.effects_observed, report.simulated, report.failed) != (5, 5, 0):
        raise ValueError("C0045 counts differ from the reviewed scope")
    return report
