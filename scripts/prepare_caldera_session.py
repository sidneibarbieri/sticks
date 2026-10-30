"""Enroll one fresh guest agent and retain its boot-bound operation identity."""

import argparse
import sys
from pathlib import Path
from uuid import UUID, uuid4

ARTIFACT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT_ROOT / "src"))

from adapters.caldera_dispatch import CalderaDispatchIntent, command_digest
from adapters.caldera_operations import CalderaOperations
from runners.caldera_lab_bootstrap import deploy_agent, guest_command, laboratory_transport, wait_for_agent
from runners.caldera_session import CalderaSession


def portable_lab_root(lab_root: Path) -> Path:
    """Name the laboratory relative to the artifact root, where the runner executes.

    The session is retained as run evidence, so it must not carry the operator's
    absolute path.
    """
    resolved = lab_root.resolve()
    if not resolved.is_relative_to(ARTIFACT_ROOT):
        raise ValueError("CALDERA laboratory must lie inside the artifact root")
    return resolved.relative_to(ARTIFACT_ROOT)


def prepare_session(lab_root: Path, output: Path) -> CalderaSession:
    if output.exists():
        raise FileExistsError(output)
    recorded_lab_root = portable_lab_root(lab_root)
    pinned_commit = "b24f6e7a99cab19cbf417009bda9b9c6c81abc31"
    actual = guest_command(lab_root, "caldera", "sudo git -C /opt/caldera rev-parse HEAD && sudo git -C /opt/caldera diff --exit-code -- server.py")
    if actual != pinned_commit:
        raise ValueError("CALDERA source differs from the pinned runtime")
    before = UUID(guest_command(lab_root, "target-linux-1", "cat /proc/sys/kernel/random/boot_id"))
    group = "sticks-campaign-" + uuid4().hex
    transport = laboratory_transport(lab_root)
    deploy_agent(lab_root, group, "/tmp/" + group)
    agent_id = wait_for_agent(transport, group)
    after = UUID(guest_command(lab_root, "target-linux-1", "cat /proc/sys/kernel/random/boot_id"))
    if before != after:
        raise ValueError("Target rebooted while registering the agent")
    operation_id = CalderaOperations(transport).create_operation(group, group)
    session = CalderaSession(
        lab_root=recorded_lab_root, target_boot_id=after,
        binding=CalderaDispatchIntent(
            operation_id=operation_id, group=group, agent_id=agent_id,
            host="target-linux-1", principal="ubuntu", platform="linux", executor="sh",
            command_sha256=command_digest("session binding; each command is bound separately"),
        ),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as destination:
        destination.write(session.model_dump_json(indent=2) + "\n")
    return session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    prepare_session(args.lab_root, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
