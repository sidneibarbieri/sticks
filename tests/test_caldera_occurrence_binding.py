"""A native link must remain bound to the observed occurrence's exact contract."""

from types import SimpleNamespace

import pytest

from adapters.caldera_dispatch import command_digest
from runners.caldera_journal import verify_occurrence_bindings
from runners.caldera_occurrence_binding import CalderaOccurrenceBinding
from runners.capability_facts import FactScope
from runners.runtime_dispatch_scope import current_dispatch_contract, runtime_dispatch_scope
from runners.runtime_step_contracts import RuntimeStepContract


def contract(occurrence=1):
    return RuntimeStepContract(
        campaign_id="0.shadowray", occurrence=occurrence, technique_id="T1082",
        executor_id="reviewed.executor", executor_sha256="a" * 64,
        mode="real_controlled", requirements=(), observers=(),
        scope=FactScope(
            run_id="run", environment_id="lab", epoch="boot", locus="target",
            host_id="target-linux-1", principal="rayuser",
        ),
    )


def test_dispatch_scope_resets_after_executor_failure():
    assert current_dispatch_contract() is None
    with pytest.raises(RuntimeError, match="executor failure"):
        with runtime_dispatch_scope(contract()):
            assert current_dispatch_contract() == contract()
            raise RuntimeError("executor failure")
    assert current_dispatch_contract() is None


@pytest.mark.parametrize("mutation", [None, "command", "contract", "missing", "duplicate"])
def test_journal_rejects_substituted_or_missing_occurrence(tmp_path, mutation):
    expected = contract()
    digest = command_digest("hostname")
    directory = tmp_path / "caldera-dispatch/command-0001"
    directory.mkdir(parents=True)
    record = CalderaOccurrenceBinding(
        contract=contract(2) if mutation == "contract" else expected,
        command_sha256=command_digest("other") if mutation == "command" else digest,
    )
    if mutation != "missing":
        (directory / "occurrence-binding.json").write_text(record.model_dump_json())
    result = SimpleNamespace(dispatch=SimpleNamespace(command_sha256=digest))
    results = (result,)
    if mutation == "duplicate":
        second = tmp_path / "caldera-dispatch/command-0002"
        second.mkdir()
        (second / "occurrence-binding.json").write_text(record.model_dump_json())
        results += (result,)
    report = SimpleNamespace(
        campaign_id="0.shadowray",
        steps=(SimpleNamespace(status="observed", contract=expected),),
    )
    if mutation is None:
        verify_occurrence_bindings(tmp_path, report, results)
    else:
        with pytest.raises(ValueError):
            verify_occurrence_bindings(tmp_path, report, results)


def test_occurrence_is_durable_before_native_submission(tmp_path, monkeypatch):
    from adapters.caldera_dispatch import CalderaDispatchIntent
    from adapters.caldera_operations import CalderaOperations
    from executors.lab_transport import TargetCommand
    from runners import caldera_target_transport as module

    binding = CalderaDispatchIntent(
        operation_id="operation", group="group", agent_id="agent",
        host="target-linux-1", principal="rayuser", platform="linux", executor="sh",
        command_sha256=command_digest("session"),
    )
    journal_root = tmp_path / "journal"

    def native(method, path, payload):
        if method == "POST":
            retained = CalderaOccurrenceBinding.model_validate_json(
                (journal_root / "command-0001/occurrence-binding.json").read_bytes()
            )
            assert retained.contract == contract()
            assert retained.command_sha256 == command_digest(payload["executor"]["command"])
        return {"id": "link", "status": 0, "finish": "timestamp"}

    monkeypatch.setattr(module, "retain_completed_command", lambda *_: SimpleNamespace(
        process_exit_code=0, stdout="target", stderr="",
    ))
    transport = module.CalderaTargetTransport(CalderaOperations(native), binding, journal_root)
    with runtime_dispatch_scope(contract()):
        transport(TargetCommand("target-linux-1", "hostname", 30, "rayuser"))


def test_c0045_dispatch_population_keeps_controller_simulations_separate():
    from runners.c0045_full_runtime_contracts import c0045_native_occurrences
    from runners.caldera_campaign_support import CALDERA_AGENT_IDENTITIES

    assert c0045_native_occurrences() == frozenset({1, 3, 4, 5, 6, 7, 8, 10})
    assert CALDERA_AGENT_IDENTITIES["0.shadowray"].principal == "rayuser"


@pytest.mark.parametrize("commands,simulated_commands", [(8, 3), (7, 3), (8, 6)])
def test_v2_counts_native_simulations_without_certifying_them(commands, simulated_commands):
    from runners.caldera_journal import CalderaJournalVerificationV2

    values = dict(
        commands=commands, observed=5, simulated=5, observed_target=5,
        observed_controller=0, simulated_target_commands=simulated_commands,
    )
    if (commands, simulated_commands) == (8, 3):
        result = CalderaJournalVerificationV2(**values)
        assert result.observed == 5
        assert result.simulated == 5
    else:
        with pytest.raises(ValueError):
            CalderaJournalVerificationV2(**values)
