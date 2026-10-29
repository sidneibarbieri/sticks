"""Preselect a bounded guest CPU command before a C0045 treatment launch."""

import hashlib
import re
import shlex

from runners.capability_facts import Digest, ImmutableRecord
from runners.c0045_compute_study import load_c0045_compute_study


WORKLOAD_CODE = """import hashlib
import sys
import time

deadline = time.monotonic() + int(sys.argv[2])
counter = 0
while time.monotonic() < deadline:
    hashlib.sha256(str(counter).encode()).digest()
    counter += 1
"""


class C0045ComputeCommand(ImmutableRecord):
    """Frozen argv identity and a launch command, not an observed effect."""

    nonce: str
    duration_seconds: int
    expected_command_sha256: Digest
    launch_script: str


def build_c0045_compute_command(nonce: str) -> C0045ComputeCommand:
    """Bind a fresh nonce to the reviewed guest argv before execution."""
    if re.fullmatch(r"[A-Za-z0-9_-]{16,128}", nonce) is None:
        raise ValueError("C0045 nonce must be a bounded literal identifier")
    study = load_c0045_compute_study()
    if hashlib.sha256(WORKLOAD_CODE.encode("utf-8")).hexdigest() != study.workload_code_sha256:
        raise ValueError("C0045 workload source differs from its study manifest")
    argv = ("python3", "-c", WORKLOAD_CODE, nonce, str(study.workload_duration_seconds))
    command_bytes = b"\0".join(argument.encode("utf-8") for argument in argv) + b"\0"
    launch_script = (
        f"setsid python3 -c {shlex.quote(WORKLOAD_CODE)} "
        f"{shlex.quote(nonce)} {study.workload_duration_seconds} "
        ">/dev/null 2>&1 </dev/null & echo $!"
    )
    return C0045ComputeCommand(
        nonce=nonce,
        duration_seconds=study.workload_duration_seconds,
        expected_command_sha256=hashlib.sha256(command_bytes).hexdigest(),
        launch_script=launch_script,
    )
