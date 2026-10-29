"""Instrument only the reviewed read-only C0045 commands, then hand off acquisition."""

import hashlib
import shlex
import subprocess
from collections.abc import Callable
from uuid import uuid4

from pydantic import model_validator

from executors.c0045_readonly_commands import TraceKind, TraceNonce, command_spec
from executors.lab_transport import run_bash_on_target_vm
from runners.c0045_fixture_contract import execution_trace_path
from runners.capability_facts import Digest, ImmutableRecord


class C0045TraceSelection(ImmutableRecord):
    kind: TraceKind
    nonce: TraceNonce
    command_sha256: Digest

    @model_validator(mode="after")
    def validate_command(self):
        expected = hashlib.sha256(command_spec(self.kind).script.encode()).hexdigest()
        if self.command_sha256 != expected:
            raise ValueError("Trace selection differs from the reviewed command")
        return self


def run_traced_readonly_step(
    sut_profile_id: str,
    kind: TraceKind,
    observer: Callable[[C0045TraceSelection], bool],
    *,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    if sut_profile_id != "0.shadowray":
        raise ValueError("C0045 traced execution requires its declared profile")
    spec = command_spec(kind)
    nonce = uuid4().hex
    path = execution_trace_path(nonce)
    script = (
        "set -eu; umask 077; test ! -e " + shlex.quote(path) + "; "
        "exec strace -f -s 16384 -e trace=%process,socket,sendmsg,sendto,recvmsg,recvfrom "
        "-o " + shlex.quote(path) + " /bin/bash -c " + shlex.quote(spec.script)
    )
    process = run_bash_on_target_vm(
        sut_profile_id, script, execution_user="rayuser", timeout=timeout
    )
    process.check_returncode()
    observer(
        C0045TraceSelection(
            kind=kind,
            nonce=nonce,
            command_sha256=hashlib.sha256(spec.script.encode()).hexdigest(),
        )
    )
    return process
