"""Collect a bounded CPU sample through the declared target-guest channel.

The returned sample is a measurement, not an authorized campaign fact.
"""

import hashlib
import json
import shlex
from pathlib import Path

from pydantic import Field

from executors.lab_transport import run_bash_on_target_vm
from runners.capability_facts import Digest, FactScope, Identity, ImmutableRecord
from runners.lab_bootstrap_observer import _check_profile_principal
from runners.runtime_diagnostics import parse_guest_reply
from runners.target_compute_predicate import TargetProcessCpuSample


_PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts/probe_target_process_cpu.py"
_MAX_PROBE_BYTES = 65536


class TargetCpuSampleRequest(ImmutableRecord):
    sut_profile_id: Identity
    scope: FactScope
    process_id: int = Field(strict=True, gt=0)
    nonce: Identity
    command_sha256: Digest


class GuestCpuReply(ImmutableRecord):
    nonce: Identity
    process_id: int = Field(strict=True, gt=0)
    process_start_ticks: int = Field(strict=True, ge=0)
    process_command_sha256: Digest
    monotonic_ns: int = Field(strict=True, gt=0)
    user_cpu_ticks: int = Field(strict=True, ge=0)
    system_cpu_ticks: int = Field(strict=True, ge=0)
    boot_id: Identity
    hostname: Identity
    principal: Identity


class GuestCpuAcquisition(ImmutableRecord):
    """A validated sample with the exact bounded guest JSON retained."""

    sample: TargetProcessCpuSample
    reply_json: str
    probe_source_sha256: Digest


def _guest_script(request: TargetCpuSampleRequest, source: str) -> str:
    arguments = {
        "process_id": request.process_id,
        "expected_nonce": request.nonce,
        "expected_command_sha256": request.command_sha256,
        "expected_boot_id": request.scope.epoch,
        "expected_host_id": request.scope.host_id,
        "expected_principal": request.scope.principal,
    }
    code = (
        "import json; "
        "module={'__name__':'target_process_cpu_probe'}; "
        f"exec({source!r},module); "
        f"print(json.dumps(module['collect_procfs_counters'](**{arguments!r})))"
    )
    return f"python3 -c {shlex.quote(code)}"


def acquire_guest_cpu_sample(request: TargetCpuSampleRequest) -> GuestCpuAcquisition:
    """Validate and retain one guest reply without granting a campaign fact."""
    scope = request.scope
    if scope.locus != "target" or scope.principal in {None, "root"}:
        raise ValueError("CPU sample requires a declared non-root target principal")
    _check_profile_principal(request.sut_profile_id, scope.host_id, scope.principal)
    source = _PROBE_PATH.read_bytes()
    if len(source) > _MAX_PROBE_BYTES:
        raise ValueError("Guest CPU probe exceeds its source size bound")
    result = run_bash_on_target_vm(
        request.sut_profile_id,
        _guest_script(request, source.decode("utf-8")),
        execution_user=scope.principal,
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError("Guest CPU probe failed; no sample was acquired")
    reply = parse_guest_reply(
        result, lambda content: GuestCpuReply.model_validate(json.loads(content))
    )
    if (
        reply.nonce != request.nonce
        or reply.process_id != request.process_id
        or reply.process_command_sha256 != request.command_sha256
        or reply.boot_id != scope.epoch
        or reply.hostname != scope.host_id
        or reply.principal != scope.principal
    ):
        raise ValueError("Guest CPU reply does not match its selected scope")
    sample = TargetProcessCpuSample(
        scope=scope,
        process_id=reply.process_id,
        process_start_ticks=reply.process_start_ticks,
        process_command_sha256=reply.process_command_sha256,
        monotonic_ns=reply.monotonic_ns,
        user_cpu_ticks=reply.user_cpu_ticks,
        system_cpu_ticks=reply.system_cpu_ticks,
    )
    return GuestCpuAcquisition(
        sample=sample,
        reply_json=result.stdout,
        probe_source_sha256=hashlib.sha256(source).hexdigest(),
    )


def collect_guest_cpu_sample(request: TargetCpuSampleRequest) -> TargetProcessCpuSample:
    """Return one validated target sample; never infer an effect from exit status."""
    return acquire_guest_cpu_sample(request).sample
