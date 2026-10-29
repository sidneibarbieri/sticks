"""A campaign objective is met by observation only through an observed producer step."""

import json

import pytest

from scripts.audit_typed_campaign_outcomes import verify_retained_observations
from runners.campaign_objective import (
    CampaignObjective,
    ObjectiveClause,
    validate_objective,
    verify_objective_receipts,
)
from runners.capability_facts import CapabilityFact, FactScope, ObservationReference
from runners.capability_observations import PredicateObservation, retain_observation
from runners.runtime_campaign_report import (
    RuntimeCampaignReport,
    RuntimeCampaignStep,
    parse_retained_campaign_report,
)
from runners.runtime_invocation import (
    RuntimeInvocationOutcome,
    RuntimeOccurrenceOutcome,
)
from runners.runtime_step_contracts import RuntimeStepContract

EXECUTOR = "executors.example.execute"
OBSERVER = "c0010-transfer"
PREDICATE = "target:benign_payload_transferred"


def _scope(
    locus: str, *, host_id: str | None = None, principal: str | None = None
) -> FactScope:
    return FactScope(
        run_id="run-a",
        environment_id="lab-a",
        epoch="boot-a",
        locus=locus,
        host_id=host_id or locus,
        principal=principal,
    )


def _observation(predicate_id: str = PREDICATE) -> ObservationReference:
    return ObservationReference(
        authority_id=OBSERVER,
        predicate_id=predicate_id,
        record_path="observations/effect.json",
        record_sha256="b" * 64,
    )


def _fact(
    name: str, origin: str, locus: str, occurrence: int, observation=None
) -> CapabilityFact:
    return CapabilityFact(
        name=name,
        origin=origin,
        scope=_scope(locus),
        producer_occurrence=occurrence,
        observation=observation if origin == "observed" else None,
    )


def _observed_step(
    fact: CapabilityFact, reference: ObservationReference
) -> RuntimeCampaignStep:
    contract = RuntimeStepContract(
        campaign_id="0.c0010",
        occurrence=fact.producer_occurrence,
        technique_id="T1048.003",
        executor_id=EXECUTOR,
        executor_sha256="a" * 64,
        mode="real_controlled",
        scope=fact.scope,
        requirements=(),
        observers=(OBSERVER,),
    )
    invocation = RuntimeInvocationOutcome(
        executor_id=EXECUTOR,
        executor_completed=True,
        stdout="",
        stderr="",
        artifacts=(),
        declared_products=(fact.name,),
    )
    observation = PredicateObservation(
        scope=fact.scope,
        predicate_id=reference.predicate_id,
        passed=True,
        established_facts=(fact.name,),
        details={},
    )
    outcome = RuntimeOccurrenceOutcome(
        invocation=invocation,
        observations=(observation,),
        observation_references=(reference,),
        authorizing_facts=(fact,),
    )
    return RuntimeCampaignStep(contract=contract, status="observed", outcome=outcome)


def _report(facts, steps=()) -> RuntimeCampaignReport:
    return RuntimeCampaignReport(
        schema_version="runtime-campaign/v2",
        campaign_id="0.c0010",
        run_id="run-a",
        infrastructure_provider="qemu",
        bootstrap=None,
        steps=tuple(steps),
        runtime_facts=tuple(facts),
        journal_references=(),
    )


def _objective(*clauses: ObjectiveClause) -> CampaignObjective:
    return CampaignObjective(
        campaign_id="0.c0010", description="reach the staged data", clauses=clauses
    )


def test_objective_met_through_an_observed_producer_step() -> None:
    reference = _observation()
    fact = _fact("exfiltrated_dataset", "observed", "target", 3, reference)
    report = _report([fact], [_observed_step(fact, reference)])
    verdict = validate_objective(
        report, _objective(ObjectiveClause(fact="exfiltrated_dataset", locus="target"))
    )
    assert verdict.achieved
    assert verdict.achieved_via_observation
    assert verdict.clauses[0].observation_bound
    assert verdict.clauses[0].producer_occurrence == 3


def test_objective_rejects_effect_on_another_target_host() -> None:
    reference = _observation()
    fact = _fact("exfiltrated_dataset", "observed", "target", 3, reference)
    report = _report([fact], [_observed_step(fact, reference)])
    objective = _objective(
        ObjectiveClause(
            fact="exfiltrated_dataset", locus="target", host_id="intended-target"
        )
    )

    verdict = validate_objective(report, objective)

    assert not verdict.achieved
    assert not verdict.achieved_via_observation


def test_objective_rejects_effect_under_another_principal() -> None:
    reference = _observation()
    fact = _fact("exfiltrated_dataset", "observed", "target", 3, reference)
    report = _report([fact], [_observed_step(fact, reference)])
    objective = _objective(
        ObjectiveClause(
            fact="exfiltrated_dataset", locus="target", principal="lab-user"
        )
    )

    verdict = validate_objective(report, objective)

    assert not verdict.achieved
    assert not verdict.achieved_via_observation


def test_objective_accepts_matching_host_and_principal() -> None:
    reference = _observation()
    fact = _fact("exfiltrated_dataset", "observed", "target", 3, reference)
    fact = fact.model_copy(
        update={"scope": _scope("target", host_id="target-a", principal="lab-user")}
    )
    report = _report([fact], [_observed_step(fact, reference)])
    objective = _objective(
        ObjectiveClause(
            fact="exfiltrated_dataset",
            locus="target",
            host_id="target-a",
            principal="lab-user",
        )
    )

    verdict = validate_objective(report, objective)

    assert verdict.achieved_via_observation


def test_one_observed_host_does_not_satisfy_two_host_objective() -> None:
    reference = _observation()
    fact = _fact("exfiltrated_dataset", "observed", "target", 3, reference)
    fact = fact.model_copy(
        update={"scope": _scope("target", host_id="host-a", principal="lab-user")}
    )
    report = _report([fact], [_observed_step(fact, reference)])
    objective = _objective(
        ObjectiveClause(fact=fact.name, locus="target", host_id="host-a"),
        ObjectiveClause(fact=fact.name, locus="target", host_id="host-b"),
    )

    verdict = validate_objective(report, objective)

    assert verdict.clauses[0].observation_bound
    assert not verdict.clauses[1].observation_bound
    assert not verdict.achieved


def _retained_objective_report(run_root):
    observation = PredicateObservation(
        scope=_scope("target"),
        predicate_id=PREDICATE,
        passed=True,
        established_facts=("exfiltrated_dataset",),
        details={},
    )
    reference = retain_observation(
        observation, authority_id=OBSERVER, run_root=run_root
    )
    fact = _fact("exfiltrated_dataset", "observed", "target", 3, reference)
    return _report([fact], [_observed_step(fact, reference)]), reference


def test_objective_receipt_verification_accepts_retained_bytes(tmp_path) -> None:
    report, _ = _retained_objective_report(tmp_path)
    objective = _objective(ObjectiveClause(fact="exfiltrated_dataset", locus="target"))

    verdict = verify_objective_receipts(report, objective, tmp_path)

    assert verdict.achieved_via_observation


def test_objective_receipt_verification_rejects_tampered_bytes(tmp_path) -> None:
    report, reference = _retained_objective_report(tmp_path)
    objective = _objective(ObjectiveClause(fact="exfiltrated_dataset", locus="target"))
    (tmp_path / reference.record_path).write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="digest"):
        verify_objective_receipts(report, objective, tmp_path)


def test_typed_outcome_audit_verifies_retained_observation(tmp_path) -> None:
    report, _ = _retained_objective_report(tmp_path)

    verify_retained_observations(report, tmp_path)


def test_typed_outcome_audit_rejects_tampered_observation(tmp_path) -> None:
    report, reference = _retained_objective_report(tmp_path)
    (tmp_path / reference.record_path).write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="digest"):
        verify_retained_observations(report, tmp_path)


def test_retained_report_parser_accepts_computed_counters() -> None:
    report = _report([])

    parsed = parse_retained_campaign_report(report.model_dump_json())

    assert parsed == report


def test_retained_report_parser_rejects_false_counter() -> None:
    payload = _report([]).model_dump(mode="json")
    payload["effects_observed"] = 1

    with pytest.raises(ValueError, match="inconsistent effects_observed"):
        parse_retained_campaign_report(json.dumps(payload))


def test_retained_report_parser_rejects_unknown_field() -> None:
    payload = _report([]).model_dump(mode="json")
    payload["unverified_success"] = True

    with pytest.raises(ValueError, match="extra_forbidden"):
        parse_retained_campaign_report(json.dumps(payload))


def test_injected_fact_without_a_producer_step_is_not_observation_bound() -> None:
    reference = _observation()
    fact = _fact("exfiltrated_dataset", "observed", "target", 3, reference)
    report = _report([fact])  # fact present, but no step produced it
    verdict = validate_objective(
        report, _objective(ObjectiveClause(fact="exfiltrated_dataset"))
    )
    assert not verdict.achieved
    assert not verdict.clauses[0].observation_bound


def test_tampered_evidence_unbinds_the_observation() -> None:
    produced = _observation("effect-present")
    other = _observation(PREDICATE)
    other = other.model_copy(update={"record_sha256": "c" * 64})
    fact = _fact("exfiltrated_dataset", "observed", "target", 3, other)
    # the step binds a different observation reference than the fact carries
    report = _report([fact], [_observed_step(fact, produced)])
    verdict = validate_objective(
        report, _objective(ObjectiveClause(fact="exfiltrated_dataset"))
    )
    assert not verdict.clauses[0].observation_bound
    assert not verdict.achieved


def test_simulated_fact_does_not_meet_an_observed_requirement() -> None:
    fact = _fact("exfiltrated_dataset", "simulation", "target", 3)
    report = _report([fact])
    verdict = validate_objective(
        report,
        _objective(ObjectiveClause(fact="exfiltrated_dataset", require_observed=True)),
    )
    assert not verdict.achieved
    assert verdict.clauses[0].origin == "simulation"


def test_simulated_fact_meets_a_relaxed_clause_but_not_via_observation() -> None:
    fact = _fact("exfiltrated_dataset", "simulation", "target", 3)
    report = _report([fact])
    verdict = validate_objective(
        report,
        _objective(ObjectiveClause(fact="exfiltrated_dataset", require_observed=False)),
    )
    assert verdict.achieved
    assert not verdict.achieved_via_observation


def test_objective_for_another_campaign_is_rejected() -> None:
    report = _report([])
    objective = CampaignObjective(
        campaign_id="0.c0026",
        description="wrong campaign",
        clauses=(ObjectiveClause(fact="exfiltrated_dataset"),),
    )
    with pytest.raises(ValueError, match="different campaigns"):
        validate_objective(report, objective)


def test_duplicate_clauses_are_rejected() -> None:
    with pytest.raises(ValueError, match="distinct"):
        _objective(
            ObjectiveClause(fact="exfiltrated_dataset", locus="target"),
            ObjectiveClause(fact="exfiltrated_dataset", locus="target"),
        )


def test_same_fact_on_distinct_hosts_is_not_a_duplicate_clause() -> None:
    objective = _objective(
        ObjectiveClause(fact="exfiltrated_dataset", locus="target", host_id="host-a"),
        ObjectiveClause(fact="exfiltrated_dataset", locus="target", host_id="host-b"),
    )

    assert len(objective.clauses) == 2
