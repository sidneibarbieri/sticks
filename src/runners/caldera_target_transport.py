"""Dispatch frozen target scripts through one declared CALDERA agent."""

import subprocess
import time
import base64
import shlex
from collections.abc import Callable
from pathlib import Path

from adapters.caldera_dispatch import CalderaDispatchIntent, command_digest
from adapters.caldera_operations import CalderaCommand, CalderaOperations
from executors.lab_transport import TargetCommand
from runners.caldera_occurrence_binding import CalderaOccurrenceBinding
from runners.runtime_dispatch_scope import current_dispatch_contract
from runners.recorded_caldera_dispatch import retain_completed_command, submit_recorded_command


def encode_target_command(command: str) -> str:
    """Preserve multiline scripts across CALDERA's newline-stripping substitution."""
    encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
    source = (
        "import base64,os;"
        f"os.execv('/bin/sh',['sh','-c',base64.b64decode({encoded!r}).decode('utf-8')])"
    )
    return "python3 -c " + shlex.quote(source)


class CalderaTargetTransport:
    def __init__(
        self, client: CalderaOperations, binding: CalderaDispatchIntent,
        record_root: Path, *, before_dispatch: Callable[[], None] | None = None,
    ) -> None:
        if binding.platform != "linux" or binding.executor != "sh":
            raise ValueError("Target script transport requires the Linux sh executor")
        record_root.mkdir(parents=True, exist_ok=False)
        self._client = client
        self._binding = binding
        self._record_root = record_root
        self._sequence = 0
        self._before_dispatch = before_dispatch

    def __call__(self, request: TargetCommand) -> subprocess.CompletedProcess[str]:
        if request.vm_name != self._binding.host or request.principal != self._binding.principal:
            raise ValueError("Target command differs from the declared agent scope")
        if self._before_dispatch is not None:
            self._before_dispatch()
        command = CalderaCommand(
            agent_id=self._binding.agent_id, platform="linux", executor="sh",
            command=encode_target_command(request.command), timeout_seconds=request.timeout_seconds,
        )
        intent = CalderaDispatchIntent.model_validate({
            **self._binding.model_dump(),
            "command_sha256": command_digest(command.command),
            "timeout_seconds": command.timeout_seconds,
        })
        contract = current_dispatch_contract()
        occurrence_binding = None
        if contract is not None:
            if (
                contract.mode not in {"real_controlled", "naive_simulated"}
                or contract.scope.locus != "target"
                or contract.scope.host_id != self._binding.host
                or contract.scope.principal != self._binding.principal
            ):
                raise ValueError("Occurrence contract differs from the CALDERA target scope")
            occurrence_binding = CalderaOccurrenceBinding(
                contract=contract, command_sha256=intent.command_sha256,
            )
        self._sequence += 1
        record_dir = self._record_root / f"command-{self._sequence:04d}"
        expected = submit_recorded_command(
            self._client, intent, command, record_dir,
            occurrence_binding=occurrence_binding,
        )
        deadline = time.monotonic() + request.timeout_seconds
        while time.monotonic() < deadline:
            link = self._client.link(expected.operation_id, expected.link_id)
            if link.get("finish"):
                result = retain_completed_command(self._client, record_dir)
                if result.process_exit_code is None:
                    raise ValueError("Target executor requires an explicit native exit code")
                return subprocess.CompletedProcess(
                    ["caldera", expected.operation_id, expected.link_id],
                    result.process_exit_code, result.stdout, result.stderr,
                )
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
        raise TimeoutError("CALDERA target command completion unavailable; submission retained")
