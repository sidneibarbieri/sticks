"""Read target process CPU counters without using executor-authored output.

This function must run inside the target guest through an authenticated,
read-only observer channel. It does not establish campaign causality by itself.
"""

from pathlib import Path

from scripts.probe_target_process_cpu import collect_procfs_counters
from runners.capability_facts import FactScope
from runners.target_compute_predicate import TargetProcessCpuSample


def collect_target_process_cpu_sample(
    scope: FactScope,
    process_id: int,
    *,
    expected_nonce: str,
    expected_command_sha256: str,
    proc_root: Path = Path("/proc"),
) -> TargetProcessCpuSample:
    """Sample a selected guest process, rejecting identity and command drift."""
    if scope.locus != "target":
        raise ValueError("CPU process sampling requires target scope")
    counters = collect_procfs_counters(
        process_id,
        expected_nonce=expected_nonce,
        expected_command_sha256=expected_command_sha256,
        expected_boot_id=scope.epoch,
        expected_host_id=scope.host_id,
        expected_principal=scope.principal or "",
        proc_root=proc_root,
    )
    if (
        counters.pop("nonce") != expected_nonce
        or counters.pop("boot_id") != scope.epoch
        or counters.pop("hostname") != scope.host_id
        or counters.pop("principal") != scope.principal
    ):
        raise ValueError("Guest sample identity differs from the declared scope")
    return TargetProcessCpuSample(scope=scope, **counters)
