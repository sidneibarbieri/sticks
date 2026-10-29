"""Explicit trace handoff must preserve the reviewed command and failures."""

import importlib
import importlib.util
import shlex
import subprocess

import pytest


def executor_module():
    assert importlib.util.find_spec("executors.c0045_trace_executor") is not None
    return importlib.import_module("executors.c0045_trace_executor")


def test_trace_handoff_binds_original_command_and_target_user(monkeypatch):
    module = executor_module()
    from executors.c0045_readonly_commands import command_spec

    captured = []

    def transport(profile, script, **kwargs):
        assert profile == "0.shadowray"
        assert kwargs["execution_user"] == "rayuser"
        assert kwargs["timeout"] == 45
        arguments = shlex.split(script)
        assert arguments[-3:] == ["/bin/bash", "-c", command_spec("python").script]
        assert "trace=%process,socket,sendmsg,sendto,recvmsg,recvfrom" in arguments
        return subprocess.CompletedProcess([], 0, "producer stdout", "")

    monkeypatch.setattr(module, "run_bash_on_target_vm", transport)
    result = module.run_traced_readonly_step(
        "0.shadowray", "python", captured.append, timeout=45
    )
    assert result.stdout == "producer stdout"
    assert len(captured) == 1
    assert captured[0].kind == "python"
    assert len(captured[0].nonce) == 32


def test_observer_failure_propagates_without_a_success_return(monkeypatch):
    module = executor_module()
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""),
    )

    def fail(selection):
        raise ValueError("retention failed")

    with pytest.raises(ValueError, match="retention failed"):
        module.run_traced_readonly_step("0.shadowray", "python", fail, timeout=45)


def test_nonzero_producer_raises_original_error_before_any_authorization(monkeypatch):
    module = executor_module()
    selected = []
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 7, "", "original failure"
        ),
    )
    with pytest.raises(subprocess.CalledProcessError) as failure:
        module.run_traced_readonly_step(
            "0.shadowray", "network", selected.append, timeout=45
        )
    assert failure.value.returncode == 7
    assert failure.value.stderr == "original failure"
    assert not selected
