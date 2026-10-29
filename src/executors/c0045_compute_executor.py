"""Launch the reviewed C0045 workload only for the prospective compute arm."""

import re
import shlex
from collections.abc import Callable
from uuid import uuid4

from pydantic import Field

from executors.c0045_compute_command import build_c0045_compute_command
from executors.lab_transport import run_bash_on_target_vm
from runners.c0045_compute_study import load_c0045_compute_study
from runners.capability_facts import Digest, Identity, ImmutableRecord


class C0045ProcessSelection(ImmutableRecord):
    """Handoff from the selected executor to an independent live observer."""

    process_id: int = Field(strict=True, gt=0)
    nonce: Identity
    command_sha256: Digest


def _launch_selected_process(sut_profile_id: str) -> C0045ProcessSelection:
    study = load_c0045_compute_study()
    nonce = uuid4().hex
    command = build_c0045_compute_command(nonce)
    result = run_bash_on_target_vm(
        sut_profile_id, command.launch_script,
        execution_user=study.target_principal, timeout=20,
    )
    result.check_returncode()
    if re.fullmatch(r"[1-9][0-9]*\n?", result.stdout) is None:
        raise ValueError("C0045 guest launch did not return one process ID")
    return C0045ProcessSelection(
        process_id=int(result.stdout.strip()), nonce=nonce,
        command_sha256=command.expected_command_sha256,
    )


def _stop_selected_process(
    sut_profile_id: str, selected: C0045ProcessSelection
) -> None:
    """Refuse cleanup when the guest PID no longer has the selected command."""
    study = load_c0045_compute_study()
    code = """import hashlib
import os
import signal
import sys

process_id = int(sys.argv[1])
expected_digest = sys.argv[2]
command_path = f"/proc/{process_id}/cmdline"
if os.path.exists(command_path):
    with open(command_path, "rb") as command_file:
        actual_digest = hashlib.sha256(command_file.read()).hexdigest()
    if actual_digest != expected_digest:
        raise ValueError("C0045 process identity changed before cleanup")
    os.kill(process_id, signal.SIGTERM)
"""
    script = "python3 -c {} {} {}".format(
        shlex.quote(code), selected.process_id,
        shlex.quote(selected.command_sha256),
    )
    result = run_bash_on_target_vm(
        sut_profile_id, script,
        execution_user=study.target_principal, timeout=20,
    )
    result.check_returncode()


def execute_c0045_compute_treatment(
    campaign_id: str,
    sut_profile_id: str,
    *,
    live_observer: Callable[[C0045ProcessSelection], bool],
) -> tuple[bool, str, str, tuple[str, ...]]:
    """Expose a live PID, then always clean up; observation owns the effect fact."""
    study = load_c0045_compute_study()
    if campaign_id != study.campaign_id or sut_profile_id != study.campaign_id:
        raise ValueError("C0045 treatment differs from the frozen campaign")
    selected = _launch_selected_process(sut_profile_id)
    try:
        live_observer(selected)
    except Exception as observation_error:
        try:
            _stop_selected_process(sut_profile_id, selected)
        except Exception as cleanup_error:
            raise ExceptionGroup(
                "C0045 observation and cleanup both failed",
                [observation_error, cleanup_error],
            ) from None
        raise
    _stop_selected_process(sut_profile_id, selected)
    return True, "C0045 bounded workload observed; verdict retained separately", "", ()
