"""CALDERA journal coverage follows target scope, not controller observations."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from runners import caldera_journal as journal
from scripts import verify_caldera_run_journal as command_line


@pytest.fixture
def mixed_run(tmp_path, monkeypatch):
    binding = SimpleNamespace(
        operation_id="operation", group="group", agent_id="agent",
        host="target-linux-1", principal="ubuntu", platform="linux", executor="sh",
    )
    session = SimpleNamespace(binding=binding, target_boot_id="boot")
    monkeypatch.setattr(journal, "CalderaSession", SimpleNamespace(
        model_validate_json=lambda _: session,
    ))
    (tmp_path / "caldera-session.json").write_text("{}")
    summary = tmp_path / "runtime-v2/run/summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text("{}")
    (tmp_path / "caldera-dispatch/command-0001").mkdir(parents=True)

    def observed(locus):
        scope = SimpleNamespace(locus=locus, epoch="boot", host_id="target-linux-1")
        observation = SimpleNamespace(passed=True, scope=scope)
        return SimpleNamespace(
            status="observed", contract=SimpleNamespace(scope=scope),
            outcome=SimpleNamespace(observations=(observation,)),
        )

    report = SimpleNamespace(
        campaign_id="0.c0010", simulated=4,
        steps=[observed("controller") for _ in range(4)] + [observed("target")],
    )
    monkeypatch.setattr(journal, "parse_retained_campaign_report", lambda _: report)
    dispatch = SimpleNamespace(**vars(binding), link_id="link")
    monkeypatch.setattr(journal, "replay_completed_command", lambda _: SimpleNamespace(dispatch=dispatch))
    return tmp_path, report


def test_controller_observations_do_not_require_native_target_commands(mixed_run):
    evidence, _ = mixed_run
    result = journal.verify_journal(evidence)
    assert result.commands == 1
    assert result.observed == 5
    assert result.observed_target == 1
    assert result.observed_controller == 4


def test_failed_occurrence_prevents_journal_qualification(mixed_run):
    evidence, report = mixed_run
    report.steps[0].status = "failed"
    with pytest.raises(ValueError, match="incomplete or failed"):
        journal.verify_journal(evidence)


def test_unaccounted_target_occurrence_is_rejected(mixed_run):
    evidence, report = mixed_run
    report.steps[0].contract.scope.locus = "target"
    with pytest.raises(ValueError, match="target occurrence count"):
        journal.verify_journal(evidence)


def test_target_observation_must_match_enrolled_boot(mixed_run):
    evidence, report = mixed_run
    report.steps[-1].outcome.observations[0].scope.epoch = "stale"
    with pytest.raises(ValueError, match="session target boot"):
        journal.verify_journal(evidence)


def test_undeclared_campaign_cannot_reuse_the_journal_contract(mixed_run):
    evidence, report = mixed_run
    report.campaign_id = "0.c0045"
    with pytest.raises(ValueError, match="no reviewed"):
        journal.verify_journal(evidence)


def test_command_line_preserves_the_existing_json_fields(mixed_run):
    evidence, _ = mixed_run
    assert command_line.verify_journal(evidence) == {
        "schema": "caldera-journal-consistency/v1",
        "commands": 1,
        "observed": 5,
        "simulated": 4,
        "observed_target": 1,
        "observed_controller": 4,
        "scope": journal.ASSURANCE_SCOPE,
    }


@pytest.mark.parametrize("field", journal.SESSION_IDENTITY_FIELDS)
def test_mismatched_dispatch_reports_only_the_field(mixed_run, monkeypatch, field):
    evidence, _ = mixed_run
    original_replay = journal.replay_completed_command

    def mismatched_dispatch(directory):
        result = original_replay(directory)
        setattr(result.dispatch, field, "untrusted-private-value")
        return result

    monkeypatch.setattr(journal, "replay_completed_command", mismatched_dispatch)
    with pytest.raises(ValueError) as failure:
        journal.verify_journal(evidence)
    assert str(failure.value) == "Retained command differs from session: " + field


def test_duplicate_native_link_cannot_cover_multiple_occurrences(mixed_run):
    evidence, report = mixed_run
    (evidence / "caldera-dispatch/command-0002").mkdir()
    report.steps.append(report.steps[-1])
    with pytest.raises(ValueError, match="Repeated CALDERA link identity"):
        journal.verify_journal(evidence)


def test_failed_target_observation_cannot_qualify(mixed_run):
    evidence, report = mixed_run
    report.steps[-1].outcome.observations[0].passed = False
    with pytest.raises(ValueError, match="session target boot"):
        journal.verify_journal(evidence)


def test_verification_record_cannot_be_mutated(mixed_run):
    evidence, _ = mixed_run
    result = journal.verify_journal(evidence)
    with pytest.raises(ValidationError, match="frozen"):
        result.commands = 2
