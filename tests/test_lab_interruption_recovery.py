"""Failed retained runs must clean up owned labs and preserve every error."""

from dataclasses import dataclass, field

import pytest

from scripts import run_lab_campaign as runner


@dataclass
class RuntimeState:
    calls: list[str] = field(default_factory=list)
    restored: bool = False
    discarded: bool = False
    failed_stage: str = "execute campaign"
    failure: BaseException | None = None
    cleanup_failure: OSError | None = None


class RecoverySnapshot:
    def __init__(self, state: RuntimeState) -> None:
        self.state = state

    def restore(self) -> None:
        self.state.restored = True

    def discard(self) -> None:
        self.state.discarded = True


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> RuntimeState:
    state = RuntimeState()

    def run_command(
        command: list[str], label: str, environment: dict[str, str] | None = None
    ) -> None:
        state.calls.append(label)
        if label == state.failed_stage and state.failure is not None:
            raise state.failure
        if label == "tear down lab" and state.cleanup_failure is not None:
            raise state.cleanup_failure

    monkeypatch.setattr(runner, "_run_command", run_command)
    monkeypatch.setattr(
        runner, "_capture_derived_state", lambda: RecoverySnapshot(state)
    )
    monkeypatch.setattr(runner, "_cleanup_runtime_outputs", lambda: None)
    return state


@pytest.mark.parametrize("failed_stage", ["bring up lab", "execute campaign"])
@pytest.mark.parametrize("failure_type", [KeyboardInterrupt, SystemExit, KeyError])
def test_interruption_cleans_owned_lab_and_retains_original_error(
    runtime: RuntimeState, failed_stage: str, failure_type: type[BaseException]
) -> None:
    runtime.failed_stage = failed_stage
    runtime.failure = failure_type("injected execution failure")

    with pytest.raises(failure_type) as failure:
        runner.main(["--campaign", "0.c0026", "--keep-lab", "--skip-collect-evidence"])

    assert failure.value is runtime.failure
    assert runtime.calls[-1] == "tear down lab"
    assert runtime.restored
    assert not runtime.discarded


@pytest.mark.parametrize("failure_type", [KeyboardInterrupt, SystemExit, KeyError])
def test_interruption_preserves_preexisting_lab(
    runtime: RuntimeState, failure_type: type[BaseException]
) -> None:
    runtime.failure = failure_type("injected execution failure")

    with pytest.raises(failure_type) as failure:
        runner.main(
            [
                "--campaign",
                "0.c0026",
                "--keep-lab",
                "--assume-lab-running",
                "--skip-collect-evidence",
            ]
        )

    assert failure.value is runtime.failure
    assert runtime.calls == ["execute campaign"]
    assert runtime.restored
    assert not runtime.discarded


@pytest.mark.parametrize("failure_type", [KeyboardInterrupt, SystemExit, KeyError])
def test_execution_and_cleanup_errors_are_both_reported(
    runtime: RuntimeState, failure_type: type[BaseException]
) -> None:
    runtime.failure = failure_type("injected execution failure")
    runtime.cleanup_failure = OSError("injected teardown failure")

    with pytest.raises(BaseExceptionGroup) as failure:
        runner.main(["--campaign", "0.c0026", "--keep-lab", "--skip-collect-evidence"])

    assert failure.value.exceptions == (runtime.failure, runtime.cleanup_failure)
    assert runtime.calls[-1] == "tear down lab"
    assert runtime.restored
    assert not runtime.discarded
