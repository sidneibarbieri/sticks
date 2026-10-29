#!/usr/bin/env python3
"""Verify strict C0045 execution prerequisites without starting a laboratory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(PROJECT_ROOT / "src"), str(PROJECT_ROOT))

from runners.strict_execution_profile import (  # noqa: E402
    StrictExecutionReceipt,
    image_tree_sha256,
    load_prepared_runtime_manifest,
    load_strict_execution_profile,
    strict_profile_sha256,
)


RECEIPT_FILENAME = "c0045-strict-preflight-receipt-v1.json"
QEMU_BOX_FORMAT = "libvirt"
SOCKET_VMNET_TRANSPORT_CHECK = PROJECT_ROOT / "scripts/apply_vagrant_qemu_socket_vmnet_fix.py"


def _run(*command: str) -> str:
    """Run a required host query and expose its native failure."""
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def _parse_version(value: str) -> tuple[int, ...]:
    """Parse a dotted tool version without accepting descriptive text."""
    match = re.fullmatch(r"(\d+(?:\.\d+)*)", value.strip())
    if match is None:
        raise ValueError(f"Unsupported tool version syntax: {value!r}")
    return tuple(int(part) for part in match.group(1).split("."))


def _vagrant_qemu_version() -> str:
    """Return exactly one installed vagrant-qemu plugin version."""
    matches = re.findall(
        r"^vagrant-qemu \(([^,]+),", _run("vagrant", "plugin", "list"), re.MULTILINE
    )
    if len(matches) != 1:
        raise RuntimeError("Strict C0045 mode requires exactly one vagrant-qemu plugin")
    return matches[0]


def _installed_box_provider(
    box_name: str, box_version: str, expected_provider: str
) -> str:
    """Find one pinned ARM64 box for the provider declared by the profile."""
    pattern = re.compile(
        rf"^{re.escape(box_name)}\s+\(\s*({re.escape(expected_provider)})\s*,\s*"
        rf"{re.escape(box_version)}\s*,\s*\(arm64\)\s*\)$"
    )
    matches = [
        pattern.fullmatch(line.strip())
        for line in _run("vagrant", "box", "list").splitlines()
    ]
    providers = [match.group(1) for match in matches if match is not None]
    if len(providers) != 1:
        raise RuntimeError(
            "Strict C0045 mode requires exactly one pinned ARM64 Vagrant box for "
            f"provider {expected_provider}"
        )
    return providers[0]


def _box_directory(box_name: str, box_version: str, provider: str) -> Path:
    """Resolve Vagrant's local immutable box directory from the chosen provider."""
    vagrant_home = Path(os.environ.get("VAGRANT_HOME", "~/.vagrant.d")).expanduser()
    escaped_name = box_name.replace("/", "-VAGRANTSLASH-")
    return vagrant_home / "boxes" / escaped_name / box_version / "arm64" / provider


def _require_declared_provider(actual_provider: str, expected_provider: str) -> None:
    """Reject an image whose Vagrant provider differs from the frozen contract."""
    if actual_provider != expected_provider:
        raise RuntimeError(
            "Strict C0045 image provider differs from the frozen profile: "
            f"expected {expected_provider}, found {actual_provider}"
        )


def _require_live_socket(socket_path: Path) -> None:
    """Reject a stale socket pathname before a multi-host lab can start."""
    if not socket_path.is_socket():
        raise RuntimeError(f"socket_vmnet socket is absent: {socket_path}")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(str(socket_path))


def _require_single_socket_vmnet_daemon() -> None:
    """Match the single-daemon condition enforced by the lab launcher."""
    binary = "/opt/homebrew/opt/socket_vmnet/bin/socket_vmnet"
    processes = _run("ps", "-axo", "pid=,command=").splitlines()
    daemon_pids = []
    for process in processes:
        fields = process.strip().split(maxsplit=1)
        if len(fields) == 2 and fields[1].startswith(binary + " "):
            daemon_pids.append(fields[0])
    if len(daemon_pids) != 1:
        raise RuntimeError(
            f"Strict C0045 requires exactly one socket_vmnet daemon; found {len(daemon_pids)}"
        )


def _require_documented_socket_vmnet_transport() -> None:
    """Reject a provider that would select QEMU's incompatible stream route."""
    subprocess.run(
        [sys.executable, str(SOCKET_VMNET_TRANSPORT_CHECK), "--check"],
        check=True,
        capture_output=True,
        text=True,
    )


def create_receipt(output_dir: Path) -> StrictExecutionReceipt:
    """Run all fail-closed strict-mode checks and write one immutable receipt."""
    profile = load_strict_execution_profile()
    prepared_runtime = load_prepared_runtime_manifest(profile)
    vagrant_qemu_version = _vagrant_qemu_version()
    if _parse_version(vagrant_qemu_version) < _parse_version(
        profile.minimum_vagrant_qemu_version
    ):
        raise RuntimeError("vagrant-qemu is older than the frozen strict-mode minimum")
    socket_path = Path(
        os.environ.get(
            "STICKS_SOCKET_VMNET_SOCKET", "/opt/homebrew/var/run/socket_vmnet"
        )
    )
    _require_live_socket(socket_path)
    _require_single_socket_vmnet_daemon()
    _require_documented_socket_vmnet_transport()
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / RECEIPT_FILENAME
    box_providers = {}
    image_fingerprints = {}
    for vm_name, image in prepared_runtime.images.items():
        _require_declared_provider(image.box_provider, QEMU_BOX_FORMAT)
        box_provider = _installed_box_provider(
            image.box_name, image.box_version, image.box_provider
        )
        _require_declared_provider(box_provider, image.box_provider)
        image_fingerprint = image_tree_sha256(
            _box_directory(image.box_name, image.box_version, box_provider)
        )
        if image_fingerprint != image.image_fingerprint_sha256:
            raise RuntimeError(
                f"Installed C0045 {vm_name} image differs from its attestation"
            )
        box_providers[vm_name] = box_provider
        image_fingerprints[vm_name] = image_fingerprint
    receipt = StrictExecutionReceipt(
        schema_version="c0045-strict-preflight-receipt/v2",
        profile_sha256=strict_profile_sha256(),
        requirements_lock_sha256=profile.requirements_lock_sha256,
        prepared_runtime_manifest_sha256=profile.prepared_runtime_manifest_sha256,
        image_fingerprint_sha256=hashlib.sha256(
            json.dumps(image_fingerprints, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        vagrant_version=_run("vagrant", "--version").strip(),
        vagrant_qemu_version=vagrant_qemu_version,
        box_providers=box_providers,
        socket_path=str(socket_path),
    )
    if receipt_path.exists():
        retained = StrictExecutionReceipt.model_validate_json(receipt_path.read_bytes())
        if retained != receipt:
            raise ValueError(
                "Retained strict preflight receipt differs from current host state"
            )
        return retained
    receipt_path.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    options = parser.parse_args()
    print(
        json.dumps(
            create_receipt(options.output_dir).model_dump(), indent=2, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
