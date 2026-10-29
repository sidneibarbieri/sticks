"""Replay consistency checks must reject unrelated or incomplete traces."""

import importlib
import importlib.util
import json

import pytest


def assess(trace, script="python3 -", kind="python"):
    assert importlib.util.find_spec("runners.guest_execution_trace") is not None
    module = importlib.import_module("runners.guest_execution_trace")
    return module.assess_execution_trace(trace, expected_script=script, kind=kind)


def trace_python():
    return (
        "\n".join(
            [
                '100 execve("/bin/bash", ["/bin/bash", "-c", "python3 -"], 0x0 /* env */) = 0',
                "100 clone(child_stack=NULL, flags=SIGCHLD) = 101",
                '101 execve("/usr/bin/python3", ["python3", "-"], 0x0 /* env */) = 0',
                "101 +++ exited with 0 +++",
                "100 +++ exited with 0 +++",
            ]
        )
        + "\n"
    )


def test_original_interpreter_and_terminal_status_are_required():
    result = assess(trace_python())
    assert result.accepted
    assert result.process_ids == (101,)
    assert not result.failed_conditions


def test_unrelated_process_cannot_satisfy_python_execution():
    trace = trace_python().replace(
        "100 clone(child_stack=NULL, flags=SIGCHLD) = 101\n", ""
    )
    result = assess(trace)
    assert not result.accepted
    assert "python_process" in result.failed_conditions


@pytest.mark.parametrize("change", ["script", "interpreter_exit", "root_exit"])
def test_wrong_command_or_failed_process_does_not_pass(change):
    trace = trace_python()
    if change == "script":
        trace = trace.replace('"python3 -"', '"echo unrelated"')
    elif change == "interpreter_exit":
        trace = trace.replace("101 +++ exited with 0 +++", "101 +++ exited with 1 +++")
    else:
        trace = trace.replace("100 +++ exited with 0 +++", "100 +++ exited with 1 +++")
    assert not assess(trace).accepted


def test_unfinished_and_resumed_calls_preserve_process_lineage():
    trace = trace_python().replace(
        "100 clone(child_stack=NULL, flags=SIGCHLD) = 101",
        "100 clone(child_stack=NULL, flags=SIGCHLD <unfinished ...>\n"
        "100 <... clone resumed>) = 101",
    )
    assert assess(trace).accepted


def test_incomplete_syscall_is_an_error_not_a_negative_verdict():
    trace = trace_python() + "101 recvmsg(3, <unfinished ...>\n"
    with pytest.raises(ValueError, match="Incomplete"):
        assess(trace)


def test_process_creation_after_exec_cannot_authorize_lineage():
    trace = trace_python()
    birth = "100 clone(child_stack=NULL, flags=SIGCHLD) = 101\n"
    trace = trace.replace(birth, "") + birth
    assert not assess(trace).accepted


def trace_network():
    script = "ip -json address show; ip -json route show"
    lines = [
        '100 execve("/bin/bash", ["/bin/bash", "-c", '
        + json.dumps(script)
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
    return script, "\n".join(lines) + "\n"


def test_network_requires_both_original_ip_processes_and_kernel_requests():
    script, trace = trace_network()
    result = assess(trace, script, "network")
    assert result.accepted
    assert result.process_ids == (101, 102)


@pytest.mark.parametrize(
    "change", ["wrong_fd", "failed_send", "wrong_process", "missing_reply"]
)
def test_unbound_or_failed_network_evidence_is_rejected(change):
    script, trace = trace_network()
    if change == "wrong_fd":
        trace = trace.replace("102 sendto(3,", "102 sendto(8,")
    elif change == "failed_send":
        trace = trace.replace("NULL, 0) = 20", "NULL, 0) = -1 EPERM")
    elif change == "wrong_process":
        trace = trace.replace("102 sendto(", "999 sendto(")
    else:
        trace = trace.replace("102 recvmsg(3, {nlmsg_type=NLMSG_DONE}, 0) = 20\n", "")
    assert not assess(trace, script, "network").accepted


def test_later_netlink_socket_cannot_authorize_earlier_query():
    script, trace = trace_network()
    socket = "102 socket(AF_NETLINK, SOCK_RAW, NETLINK_ROUTE) = 3\n"
    trace = trace.replace(socket, "") + socket
    assert not assess(trace, script, "network").accepted


@pytest.mark.parametrize(
    "suffix", ["101 <... clone resumed>) = 102\n", "unattributed trace\n"]
)
def test_malformed_trace_is_not_a_negative_verdict(suffix):
    with pytest.raises(ValueError):
        assess(trace_python() + suffix)
