"""Replay consistency of trusted Linux strace acquisitions, not guest attestation."""

import json
import re
from dataclasses import dataclass
from typing import Literal

from runners.capability_facts import ImmutableRecord

MAX_TRACE_BYTES = 262144
MAX_TRACE_EVENTS = 8192


@dataclass(frozen=True)
class TraceEvent:
    process_id: int
    order: int
    call: str


class TraceAssessment(ImmutableRecord):
    accepted: bool
    root_process_id: int
    process_ids: tuple[int, ...]
    failed_conditions: tuple[str, ...]


def parse_trace(trace: str) -> tuple[TraceEvent, ...]:
    """Reassemble interleaved syscalls; incomplete acquisition is an error."""
    if not 0 < len(trace.encode()) <= MAX_TRACE_BYTES:
        raise ValueError("Trace outside size bound")
    lines = trace.splitlines()
    if len(lines) > MAX_TRACE_EVENTS:
        raise ValueError("Trace outside event bound")
    pending = {}
    events = []
    for order, line in enumerate(lines):
        match = re.fullmatch(r"([1-9][0-9]*)\s+(.+)", line)
        if match is None:
            raise ValueError("Malformed process trace line")
        process_id, call = int(match.group(1)), match.group(2)
        if call.endswith(" <unfinished ...>"):
            if process_id in pending:
                raise ValueError("Duplicate unfinished syscall")
            pending[process_id] = (order, call.removesuffix(" <unfinished ...>"))
            continue
        resumed = re.match(r"<\.\.\. ([a-z0-9_]+) resumed>(.*)", call)
        if resumed:
            if process_id not in pending:
                raise ValueError("Resumed syscall has no beginning")
            order, prefix = pending.pop(process_id)
            if not prefix.startswith(resumed.group(1) + "("):
                raise ValueError("Resumed syscall identity changed")
            call = prefix + resumed.group(2)
        events.append(TraceEvent(process_id, order, call))
    if pending:
        raise ValueError("Incomplete syscall acquisition")
    return tuple(sorted(events, key=lambda event: event.order))


def successful_exec(event: TraceEvent) -> tuple[str, list[str]] | None:
    if not event.call.startswith("execve(") or not re.search(r"=\s*0$", event.call):
        return None
    decoder = json.JSONDecoder()
    arguments = event.call.removeprefix("execve(")
    executable, offset = decoder.raw_decode(arguments)
    remainder = arguments[offset:].lstrip()
    if not remainder.startswith(","):
        raise ValueError("Malformed execve arguments")
    argv, _ = decoder.raw_decode(remainder[1:].lstrip())
    if (
        not isinstance(executable, str)
        or not isinstance(argv, list)
        or any(not isinstance(argument, str) for argument in argv)
    ):
        raise ValueError("Malformed or truncated execve command")
    return executable, argv


def process_parents(events: tuple[TraceEvent, ...]) -> dict[int, TraceEvent]:
    parents = {}
    for event in events:
        if re.match(r"(?:clone3?|vfork|fork)\(", event.call):
            child = re.search(r"=\s*([1-9][0-9]*)$", event.call)
            if child:
                child_id = int(child.group(1))
                if child_id in parents or child_id == event.process_id:
                    raise ValueError("Ambiguous process lineage")
                parents[child_id] = event
    return parents


def descends_from(
    process_id: int, root: int, parents: dict[int, TraceEvent], before: int
) -> bool:
    seen = set()
    while process_id in parents:
        if process_id in seen:
            raise ValueError("Cyclic process lineage")
        seen.add(process_id)
        birth = parents[process_id]
        if birth.order >= before:
            return False
        before = birth.order
        process_id = birth.process_id
        if process_id == root:
            return True
    return False


def completed(events: tuple[TraceEvent, ...], process_id: int) -> bool:
    terminals = [
        event.call
        for event in events
        if event.process_id == process_id and event.call.startswith("+++")
    ]
    return terminals == ["+++ exited with 0 +++"]


def queried_kernel(events: tuple[TraceEvent, ...], process_id: int, query: str) -> bool:
    selected = [event for event in events if event.process_id == process_id]
    descriptors = []
    for event in selected:
        match = re.match(
            r"socket\(AF_NETLINK,.*NETLINK_ROUTE\)\s*=\s*([0-9]+)$", event.call
        )
        if match:
            descriptors.append((int(match.group(1)), event.order))
    for descriptor, created in descriptors:
        requests = [
            event
            for event in selected
            if re.match(r"(?:sendto|sendmsg)\(" + str(descriptor) + r",", event.call)
            and query in event.call
            and re.search(r"=\s*[1-9][0-9]*$", event.call)
            and event.order > created
        ]
        if requests and any(
            re.match(r"(?:recvmsg|recvfrom)\(" + str(descriptor) + r",", event.call)
            and "NLMSG_DONE" in event.call
            and re.search(r"=\s*[1-9][0-9]*$", event.call)
            and event.order > requests[0].order
            for event in selected
        ):
            return True
    return False


def assess_execution_trace(
    trace: str, *, expected_script: str, kind: Literal["python", "network"]
) -> TraceAssessment:
    """Check command, lineage, successful exits and selected kernel query calls."""
    if kind not in {"python", "network"}:
        raise ValueError("Unknown execution trace kind")
    events = parse_trace(trace)
    root = events[0].process_id
    failed = []
    if successful_exec(events[0]) != (
        "/bin/bash",
        ["/bin/bash", "-c", expected_script],
    ):
        failed.append("original_command")
    if not completed(events, root):
        failed.append("root_exit")
    parents = process_parents(events)
    commands = [(event, successful_exec(event)) for event in events]
    processes = []
    selections = (
        (("python", None),)
        if kind == "python"
        else (("address", "RTM_GETADDR"), ("route", "RTM_GETROUTE"))
    )
    for command, query in selections:
        expected = (
            ["python3", "-"] if kind == "python" else ["ip", "-json", command, "show"]
        )
        paths = (
            {"/usr/bin/python3"}
            if kind == "python"
            else {"/usr/sbin/ip", "/usr/bin/ip"}
        )
        matching = [
            event.process_id
            for event, executed in commands
            if executed is not None
            and executed[0] in paths
            and executed[1] == expected
            and descends_from(event.process_id, root, parents, event.order)
        ]
        if len(matching) != 1 or not completed(events, matching[0]):
            failed.append(command + "_process")
            continue
        process_id = matching[0]
        processes.append(process_id)
        if query and not queried_kernel(events, process_id, query):
            failed.append(command + "_kernel_query")
    return TraceAssessment(
        accepted=not failed,
        root_process_id=root,
        process_ids=tuple(processes),
        failed_conditions=tuple(failed),
    )
