#!/usr/bin/env python3
"""Run one VM campaign from a separate, auditable workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

if __package__:
    from scripts.caldera_runner_secret_policy import require_safe_caldera_sources
else:
    from caldera_runner_secret_policy import require_safe_caldera_sources


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from runners.caldera_campaign_support import SUPPORTED_CALDERA_CAMPAIGNS
RUNTIME_DIRECTORIES = {
    ".mypy_cache",
    ".playwright-cli",
    ".pytest_cache",
    ".ruff_cache",
    ".vagrant",
    ".venv",
    "_private",
    "__pycache__",
}
LOCAL_FILES = {".DS_Store", ".env"}
DEFAULT_SOCKET_VMNET = Path("/opt/homebrew/var/run/socket_vmnet")
SOCKET_VMNET_BINARY = "/opt/homebrew/opt/socket_vmnet/bin/socket_vmnet"
MINIMUM_VM_HOST_FREE_BYTES = 25 * 1024**3
SOURCE_MANIFEST_SKIP_DIRS = (
    "release/evidence",
    "results/evidence",
    "release/realistic_data",
    "release/sut_reports",
)


def require_single_socket_vmnet_daemon() -> str:
    """Reject an ambiguous default macOS networking daemon before provisioning."""
    process_table = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    daemon_pids = []
    for process in process_table:
        fields = process.strip().split(maxsplit=1)
        if len(fields) == 2 and fields[1].startswith(f"{SOCKET_VMNET_BINARY} "):
            daemon_pids.append(fields[0])
    if len(daemon_pids) != 1:
        raise RuntimeError(
            "Expected exactly one socket_vmnet daemon for the default socket; "
            f"found {len(daemon_pids)}: {' '.join(daemon_pids) or 'none'}"
        )
    return daemon_pids[0]


def require_qemu_network(provider: str) -> None:
    """Fail before copying a workspace when the macOS QEMU network is down."""
    if provider != "qemu" or platform.system() != "Darwin":
        return
    socket_path = Path(
        os.environ.get("STICKS_SOCKET_VMNET_SOCKET", DEFAULT_SOCKET_VMNET)
    )
    if not socket_path.is_socket():
        raise FileNotFoundError(f"socket_vmnet socket is unavailable: {socket_path}")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        try:
            connection.connect(str(socket_path))
        except OSError as error:
            raise ConnectionError(
                f"socket_vmnet is not running at {socket_path}; start the "
                f"private-network daemon before QEMU ({error})"
            ) from error
    if socket_path == DEFAULT_SOCKET_VMNET:
        require_single_socket_vmnet_daemon()


def require_vm_host_capacity(run_root: Path) -> None:
    """Refuse VM provisioning unless the documented host-space floor is available."""
    existing_parent = run_root
    while not existing_parent.exists():
        existing_parent = existing_parent.parent
    available_bytes = shutil.disk_usage(existing_parent).free
    if available_bytes < MINIMUM_VM_HOST_FREE_BYTES:
        raise OSError(
            "Insufficient free space for VM-backed execution: "
            f"need at least {MINIMUM_VM_HOST_FREE_BYTES} bytes, "
            f"available {available_bytes} bytes"
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_manifest(
    root: Path,
    *,
    excluded_relative_roots: tuple[str, ...] = (),
) -> dict[str, object]:
    """Hash a tree, optionally excluding declared runtime-only subtrees."""
    files: list[dict[str, object]] = []
    tree_digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        if any(
            relative_path == excluded_root
            or relative_path.startswith(f"{excluded_root}/")
            for excluded_root in excluded_relative_roots
        ):
            continue
        file_digest = sha256_file(path)
        tree_digest.update(relative_path.encode("utf-8") + b"\0")
        tree_digest.update(file_digest.encode("ascii") + b"\0")
        files.append(
            {"path": relative_path, "sha256": file_digest, "size": path.stat().st_size}
        )
    return {"tree_sha256": tree_digest.hexdigest(), "files": files}


def workspace_exclusions(source: Path, directory: str, names: list[str]) -> set[str]:
    excluded = set(names) & (RUNTIME_DIRECTORIES | LOCAL_FILES)
    excluded.update(
        name
        for name in names
        if name.startswith("config.") and name.endswith(".local.json")
    )
    excluded.add("config.local.json")
    if Path(directory).resolve() == source:
        excluded.add("runs")
    if Path(directory).resolve() == source / "data":
        excluded.add("artifacts")
    return excluded


def copy_workspace(source: Path, destination: Path) -> None:
    source = source.resolve()

    def ignored(directory: str, names: list[str]) -> set[str]:
        return workspace_exclusions(source, directory, names)

    required_bytes = 0
    for directory, subdirectories, files in os.walk(source, followlinks=True):
        excluded = ignored(directory, subdirectories + files)
        subdirectories[:] = [name for name in subdirectories if name not in excluded]
        required_bytes += sum(
            (Path(directory) / name).stat().st_size
            for name in files
            if name not in excluded
        )
    existing_parent = destination.parent
    while not existing_parent.exists():
        existing_parent = existing_parent.parent
    available_bytes = shutil.disk_usage(existing_parent).free
    if required_bytes > available_bytes:
        raise OSError(
            f"Insufficient space for workspace copy: need {required_bytes} bytes, "
            f"available {available_bytes} bytes; VM disk growth is additional"
        )
    shutil.copytree(source, destination, ignore=ignored)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_logged_command(
    command: list[str], *, workspace: Path, environment: dict[str, str], log_path: Path
) -> int:
    """Stream child output with host run paths projected out of the sealed log."""
    host_run_root = str(log_path.parent.resolve()).encode("utf-8")
    with (
        log_path.open("wb") as log_file,
        subprocess.Popen(
            command,
            cwd=workspace,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as process,
    ):
        if process.stdout is None:
            raise RuntimeError("Campaign process has no output stream")
        for line in process.stdout:
            portable_line = line.replace(host_run_root, b"<RUN_ROOT>")
            log_file.write(portable_line)
            log_file.flush()
            if hasattr(sys.stdout, "buffer"):
                sys.stdout.buffer.write(portable_line)
                sys.stdout.buffer.flush()
            else:
                sys.stdout.write(portable_line.decode("utf-8", errors="replace"))
                sys.stdout.flush()
        return process.wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign", required=True, help="Campaign ID, for example 0.c0011."
    )
    parser.add_argument(
        "--provider", choices=("qemu", "libvirt", "virtualbox"), default="qemu"
    )
    parser.add_argument(
        "--run-root", type=Path, required=True, help="New directory for this run."
    )
    parser.add_argument(
        "--node-archive",
        type=Path,
        help="Optional pinned Node archive cache on the host.",
    )
    parser.add_argument(
        "--keep-lab",
        action="store_true",
        help="Keep this isolated lab for target-side observation; explicit teardown remains required.",
    )
    parser.add_argument("--caldera-session", type=Path,
                        help="Prepared isolated CALDERA session for target execution")
    parser.add_argument("--caldera-dispatch", action="store_true",
                        help="Prepare a fresh target agent after provisioning")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.caldera_session and args.caldera_dispatch:
        raise ValueError("Select either a prepared session or fresh enrollment")
    if (args.caldera_session or args.caldera_dispatch) and args.campaign not in SUPPORTED_CALDERA_CAMPAIGNS:
        raise ValueError("CALDERA session requires a reviewed C0010 or C0026 campaign")
    if args.caldera_session and not args.caldera_session.is_file():
        raise FileNotFoundError(args.caldera_session)
    if args.campaign == "0.shadowray":
        raise ValueError(
            "C0045 requires the frozen effect-series runner; "
            "run scripts/run_c0045_effect_series_cell.py instead"
        )
    run_root = args.run_root.resolve()
    if run_root.is_relative_to(PROJECT_ROOT):
        raise ValueError("Run root must be outside the source artifact")
    if args.node_archive and not args.node_archive.is_file():
        raise FileNotFoundError(args.node_archive)
    require_qemu_network(args.provider)
    require_safe_caldera_sources(PROJECT_ROOT)
    require_vm_host_capacity(run_root)

    run_root.mkdir(parents=True, exist_ok=False)
    workspace = run_root / "workspace"
    evidence = run_root / "evidence"
    copy_workspace(PROJECT_ROOT, workspace)
    source_manifest = tree_manifest(
        workspace,
        excluded_relative_roots=SOURCE_MANIFEST_SKIP_DIRS,
    )
    write_json(run_root / "source_manifest.json", source_manifest)

    environment = os.environ.copy()
    node_archive_digest = None
    if args.node_archive:
        node_archive = args.node_archive.resolve()
        environment["STICKS_NODE_ARCHIVE"] = str(node_archive)
        node_archive_digest = sha256_file(node_archive)

    started_at = datetime.now(UTC).isoformat()
    command = [
        sys.executable,
        str(workspace / "scripts" / "run_lab_campaign.py"),
        "--campaign",
        args.campaign,
        "--provider",
        args.provider,
        "--evidence-output",
        str(evidence),
    ]
    if args.caldera_session:
        command.extend(["--caldera-session", str(args.caldera_session.resolve())])
    if args.caldera_dispatch:
        command.append("--caldera-dispatch")
    if args.keep_lab:
        command.append("--keep-lab")
    log_path = run_root / "execution.log"
    print(f"Run log: {log_path}", flush=True)
    exit_code = run_logged_command(
        command, workspace=workspace, environment=environment, log_path=log_path
    )
    output_manifest = tree_manifest(evidence) if evidence.exists() else None
    artifact_directory = workspace / "data" / "artifacts"
    artifact_manifest = (
        tree_manifest(artifact_directory) if artifact_directory.exists() else None
    )
    write_json(
        run_root / "run_context.json",
        {
            "campaign_id": args.campaign,
            "provider": args.provider,
            "keep_lab_requested": args.keep_lab,
            "started_at": started_at,
            "ended_at": datetime.now(UTC).isoformat(),
            "exit_code": exit_code,
            "execution_log_path": log_path.name,
            "execution_log_sha256": sha256_file(log_path),
            "source_tree_sha256": source_manifest["tree_sha256"],
            "evidence_tree_sha256": (
                output_manifest["tree_sha256"] if output_manifest else None
            ),
            "artifact_tree_sha256": (
                artifact_manifest["tree_sha256"] if artifact_manifest else None
            ),
            "node_archive_sha256": node_archive_digest,
        },
    )
    if output_manifest:
        write_json(run_root / "evidence_manifest.json", output_manifest)
    if artifact_manifest:
        write_json(run_root / "artifact_manifest.json", artifact_manifest)
    print(f"Isolated run: {run_root}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
