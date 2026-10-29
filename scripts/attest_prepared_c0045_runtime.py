#!/usr/bin/env python3
"""Write secret-free guest inventories for prepared C0045 role images."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(PROJECT_ROOT / "src"), str(PROJECT_ROOT))

from runners.prepared_runtime_attestation import PreparedGuestInventory  # noqa: E402


Role = Literal["caldera", "attacker", "target-linux-1"]
ROLES: tuple[Role, ...] = ("caldera", "attacker", "target-linux-1")
VAGRANT_TRANSPORT_FINGERPRINT = "SHA256:1M4RzhMyWuFS/86uPY/ce2prh/dVTHW7iD2RhpquOZA"


def _guest_command(role: Role, command: str) -> str:
    """Run one read-only command through the declared Vagrant role."""
    completed = subprocess.run(
        ["vagrant", "ssh", "-c", command],
        cwd=PROJECT_ROOT / "lab" / "vagrant" / role,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _lines(value: str) -> tuple[str, ...]:
    """Return nonempty, sorted lines suitable for a stable receipt."""
    return tuple(sorted(line.strip() for line in value.splitlines() if line.strip()))


def collect_inventory(role: Role) -> PreparedGuestInventory:
    """Collect only version and readiness facts; never retain secret content."""
    hostname = _guest_command(role, "hostname").strip()
    os_release = _lines(
        _guest_command(
            role, '. /etc/os-release && printf \'%s\n%s\n\' "$ID" "$VERSION_ID"'
        )
    )
    packages = _lines(
        _guest_command(role, "dpkg-query -W -f='${binary:Package}=${Version}\n'")
    )
    python_packages = (
        _lines(_guest_command(role, "python3 -m pip freeze"))
        if any(package.startswith("python3-pip=") for package in packages)
        else ()
    )
    private_key_paths = _lines(
        _guest_command(
            role,
            "sudo -n find /home /root -xdev -type f \\( -name id_rsa -o -name id_ed25519 -o -name '*.pem' -o -name '*.key' \\) -print",
        )
    )
    transport_fingerprint = _guest_command(
        role,
        "sudo -n ssh-keygen -lf /home/vagrant/.ssh/authorized_keys "
        f"| awk '{{print $2}}' | grep -Fx '{VAGRANT_TRANSPORT_FINGERPRINT}'",
    ).strip()
    if role == "caldera":
        caldera_revision = _guest_command(
            role, "sudo -n git -C /opt/caldera rev-parse HEAD"
        ).strip()
        caldera_submodules = _lines(
            _guest_command(
                role, "sudo -n git -C /opt/caldera submodule status --recursive"
            )
        )
        active_services = _lines(_guest_command(role, "systemctl is-active caldera"))
    else:
        caldera_revision = None
        caldera_submodules = ()
        active_services = _lines(_guest_command(role, "systemctl is-active ssh"))
    return PreparedGuestInventory(
        schema_version="c0045-prepared-guest-inventory/v1",
        role=role,
        hostname=hostname,
        os_release=os_release,
        packages=packages,
        python_packages=python_packages,
        caldera_revision=caldera_revision,
        caldera_submodules=caldera_submodules,
        active_services=active_services,
        private_key_paths=private_key_paths,
        vagrant_transport_fingerprint=transport_fingerprint,
    )


def write_inventory(role: Role, output_dir: Path) -> Path:
    """Collect and atomically retain one validated role inventory."""
    inventory = collect_inventory(role)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"c0045-{role}-prepared-guest-inventory-v1.json"
    if output_path.exists():
        retained = PreparedGuestInventory.model_validate_json(output_path.read_bytes())
        if retained != inventory:
            raise ValueError(f"Retained {role} inventory differs from current VM")
        return output_path
    with tempfile.TemporaryDirectory(prefix=f"sticks-{role}-inventory-", dir=output_dir) as raw_staging:
        staging_path = Path(raw_staging) / output_path.name
        staging_path.write_text(inventory.model_dump_json(indent=2) + "\n", encoding="utf-8")
        staging_path.replace(output_path)
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    print(json.dumps({"path": str(output_path), "sha256": digest}, sort_keys=True))
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=ROLES, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    options = parser.parse_args()
    write_inventory(options.role, options.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
