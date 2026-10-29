#!/usr/bin/env python3
"""Reject a running QEMU laboratory that is not using socket_vmnet's fd route."""

from __future__ import annotations

import argparse
import json
import subprocess


def qemu_commands() -> list[str]:
    """Return live QEMU command lines without treating absent VMs as healthy."""
    result = subprocess.run(
        ["ps", "-axo", "command="], check=True, capture_output=True, text=True
    )
    return [line for line in result.stdout.splitlines() if "qemu-system" in line]


def require_documented_transport(vm_names: list[str], commands: list[str]) -> dict[str, str]:
    """Map every requested VM to one QEMU command using socket_vmnet fd 3."""
    selected: dict[str, str] = {}
    for vm_name in vm_names:
        matches = [command for command in commands if f"/vagrant/{vm_name}/" in command]
        if len(matches) != 1:
            raise RuntimeError(f"expected one live QEMU process for {vm_name}, found {len(matches)}")
        command = matches[0]
        if "-netdev stream," in command:
            raise RuntimeError(f"{vm_name} uses unsupported socket_vmnet stream transport")
        if "-netdev socket," not in command or "fd=3" not in command:
            raise RuntimeError(f"{vm_name} is not using socket_vmnet's fd 3 transport")
        selected[vm_name] = command
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vm", action="append", required=True, dest="vm_names")
    options = parser.parse_args()
    selected = require_documented_transport(options.vm_names, qemu_commands())
    print(json.dumps({"status": "pass", "vms": sorted(selected)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
