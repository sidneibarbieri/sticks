"""A retained execution trace must match scope, command and occurrence."""

import hashlib
import importlib
import importlib.util
import json
import subprocess

import pytest
from pydantic import ValidationError

from runners.capability_facts import FactScope


def observer():
    assert importlib.util.find_spec("runners.c0045_trace_observer") is not None
    return importlib.import_module("runners.c0045_trace_observer")


def request(**changes):
    fields = dict(
        sut_profile_id="0.shadowray",
        kind="python",
        nonce="a" * 32,
        producer_occurrence=7,
        scope=FactScope(
            run_id="run",
            environment_id="lab",
            epoch="boot",
            locus="target",
            host_id="target-linux-1",
            principal="rayuser",
        ),
    )
    fields.update(changes)
    return observer().C0045TraceRequest(**fields)


def reply(script=None, **changes):
    import hashlib
    from executors.c0045_readonly_commands import command_spec

    original = script if script is not None else command_spec("python").script
    trace = (
        "\n".join(
            [
                '100 execve("/bin/bash", ["/bin/bash", "-c", '
                + json.dumps(original)
                + "], 0x0) = 0",
                "100 clone(child_stack=NULL, flags=SIGCHLD) = 101",
                '101 execve("/usr/bin/python3", ["python3", "-"], 0x0) = 0',
                "101 +++ exited with 0 +++",
                "100 +++ exited with 0 +++",
            ]
        )
        + "\n"
    )
    return (
        dict(
            hostname="target-linux-1",
            principal="rayuser",
            observer_uid=1001,
            boot_id="boot",
            nonce="a" * 32,
            owner="rayuser",
            trace=trace,
            trace_sha256=hashlib.sha256(trace.encode()).hexdigest(),
        )
        | changes
    )


@pytest.mark.parametrize(
    "fields",
    [{"producer_occurrence": 8}, {"producer_occurrence": True}, {"nonce": "../escape"}],
)
def test_wrong_occurrence_or_path_challenge_is_rejected(fields):
    with pytest.raises(ValidationError):
        request(**fields)


def test_registered_python_trace_grants_only_interpreter_fact(monkeypatch, tmp_path):
    module = observer()
    selected = request()
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(reply()), ""
        ),
    )
    from runners.capability_authority import (
        acquire_registered_observation,
        verify_registered_observation,
    )

    reference = acquire_registered_observation(
        "c0045-python", selected, run_root=tmp_path
    )
    observed = verify_registered_observation(
        reference,
        run_root=tmp_path,
        expected_scope=selected.scope,
        expected_predicate="python-execution-trace",
    )
    assert observed.passed
    assert observed.established_facts == ("execution:python_interpreter_observed",)
    assert observed.producer_occurrence == 7
    assert observed.details["trace"]


def test_trace_reply_bound_allows_json_escaped_bounded_trace(monkeypatch):
    from runners.guest_execution_trace import TraceAssessment

    module = observer()
    extended_trace = "a" * 9000
    bounded_reply = reply(
        trace=extended_trace,
        trace_sha256=hashlib.sha256(extended_trace.encode()).hexdigest(),
    )
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(bounded_reply), ""
        ),
    )
    monkeypatch.setattr(
        module,
        "assess_execution_trace",
        lambda *args, **kwargs: TraceAssessment(
            accepted=True, root_process_id=1, process_ids=(1,), failed_conditions=()
        ),
    )

    assert module.observe_c0045_trace(request()).passed


@pytest.mark.parametrize(
    "changes",
    [
        {"boot_id": "old"},
        {"nonce": "b" * 32},
        {"principal": "other"},
        {"owner": "other"},
        {"hostname": "controller"},
        {"trace_sha256": "0" * 64},
    ],
)
def test_trace_identity_or_digest_mismatch_grants_nothing(monkeypatch, changes):
    module = observer()
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(reply(**changes)), ""
        ),
    )
    result = module.observe_c0045_trace(request())
    assert not result.passed
    assert not result.established_facts


def test_unrelated_script_is_not_the_reviewed_python_step(monkeypatch):
    module = observer()
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(reply(script="echo unrelated")), ""
        ),
    )
    assert not module.observe_c0045_trace(request()).passed


def test_trace_read_error_is_not_a_negative_fact(monkeypatch):
    module = observer()
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 9, "", "missing trace"),
    )
    with pytest.raises(subprocess.CalledProcessError):
        module.observe_c0045_trace(request())


def test_registered_network_trace_requires_both_kernel_queries(monkeypatch, tmp_path):
    import hashlib
    from executors.c0045_readonly_commands import command_spec

    module = observer()
    lines = [
        '100 execve("/bin/bash", ["/bin/bash", "-c", '
        + json.dumps(command_spec("network").script)
        + "], 0x0) = 0"
    ]
    for process, command, query in (
        (101, "address", "RTM_GETADDR"),
        (102, "route", "RTM_GETROUTE"),
    ):
        lines.extend(
            [
                f"100 clone(child_stack=NULL, flags=SIGCHLD) = {process}",
                f'{process} execve("/usr/sbin/ip", ["ip", "-json", "{command}", "show"], 0x0) = 0',
                f"{process} socket(AF_NETLINK, SOCK_RAW, NETLINK_ROUTE) = 3",
                f"{process} sendto(3, [{{nlmsg_type={query}}}], 20, 0, NULL, 0) = 20",
                f"{process} recvmsg(3, {{nlmsg_type=NLMSG_DONE}}, 0) = 20",
                f"{process} +++ exited with 0 +++",
            ]
        )
    lines.append("100 +++ exited with 0 +++")
    trace = "\n".join(lines) + "\n"
    response = reply(
        trace=trace, trace_sha256=hashlib.sha256(trace.encode()).hexdigest()
    )
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(response), ""
        ),
    )
    from runners.capability_authority import (
        acquire_registered_observation,
        verify_registered_observation,
    )

    selected = request(kind="network", producer_occurrence=8)
    reference = acquire_registered_observation(
        "c0045-network", selected, run_root=tmp_path
    )
    observed = verify_registered_observation(
        reference,
        run_root=tmp_path,
        expected_scope=selected.scope,
        expected_predicate="network-query-trace",
    )
    assert observed.passed
    assert observed.established_facts == ("discovery:kernel_queries_observed",)


def test_retained_verdict_cannot_be_downgraded_or_upgraded(monkeypatch, tmp_path):
    module = observer()
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(reply()), ""
        ),
    )
    observed = module.observe_c0045_trace(request())
    assert hasattr(module, "verify_c0045_trace_observation")
    module.verify_c0045_trace_observation(observed, run_root=tmp_path)
    changed = observed.model_copy(update={"passed": False, "established_facts": ()})
    with pytest.raises(ValueError, match="differs"):
        module.verify_c0045_trace_observation(changed, run_root=tmp_path)


def test_normal_runner_invokes_trace_handoff_and_grants_only_registered_fact(
    monkeypatch, tmp_path
):
    import hashlib
    import inspect
    from pathlib import Path
    from executors import c0045_trace_executor, executor_registry
    from executors.registry_initializer import initialize_registry
    from runners import campaign_runner
    from runners.runtime_step_contracts import RuntimeStepContract

    assert hasattr(campaign_runner, "C0045TraceLiveObserverBinding")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    initialize_registry(force=True)
    runner = campaign_runner.UnifiedCampaignRunner("0.shadowray", tmp_path / "output")
    scope = request().scope.model_copy(update={"run_id": runner.run_id})
    selected = executor_registry.registry.get_executor("T1059.006", "0.shadowray")
    source = Path(inspect.getsourcefile(selected))
    contract = RuntimeStepContract(
        campaign_id="0.shadowray",
        occurrence=7,
        technique_id="T1059.006",
        executor_id=selected.__module__ + "." + selected.__qualname__,
        executor_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        mode="real_controlled",
        scope=scope,
        requirements=(),
        observers=("c0045-python",),
    )
    state = {}

    def make_request(selection):
        state["nonce"] = selection.nonce
        return request(scope=scope, nonce=selection.nonce)

    monkeypatch.setattr(
        c0045_trace_executor,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, "Python version: controlled", ""
        ),
    )
    monkeypatch.setattr(
        observer(),
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(reply(nonce=state["nonce"])), ""
        ),
    )
    root = tmp_path / "retained"
    root.mkdir()
    outcome = runner.execute_contracted_occurrence(
        contract,
        {},
        run_root=root,
        selected_registry=executor_registry.registry,
        live_observer=campaign_runner.C0045TraceLiveObserverBinding(
            kind="python", request_for_trace=make_request
        ),
    )
    assert outcome.invocation.executor_completed
    assert tuple(fact.name for fact in outcome.authorizing_facts) == (
        "execution:python_interpreter_observed",
    )
