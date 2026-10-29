#!/usr/bin/env python3
"""Package one halted, prepared C0045 QEMU role as a self-contained Vagrant box."""

from __future__ import annotations

import argparse
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Literal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
Role = Literal["caldera", "attacker", "target-linux-1"]
ROLES: tuple[Role, ...] = ("caldera", "attacker", "target-linux-1")
MACHINE_NAMES: dict[Role, str] = {
    "caldera": "caldera",
    "attacker": "attacker",
    "target-linux-1": "target1",
}
HALTED_STATES = frozenset({"poweroff", "stopped"})


def _role_disk(role: Role) -> Path:
    """Return exactly one halted role overlay; ambiguity is a packaging error."""
    machine = MACHINE_NAMES[role]
    matches = sorted(
        (PROJECT_ROOT / "lab" / "vagrant" / role / ".vagrant" / "machines" / machine / "qemu").glob(
            "*/linked-box.img"
        )
    )
    if len(matches) != 1:
        raise ValueError(f"Expected one prepared {role} overlay, found {len(matches)}")
    return matches[0]


def _require_halted(role: Role) -> None:
    """Reject a disk that could still be changing under QEMU."""
    completed = subprocess.run(
        ["vagrant", "status", "--machine-readable"],
        cwd=PROJECT_ROOT / "lab" / "vagrant" / role,
        check=True,
        capture_output=True,
        text=True,
    )
    states = [
        line.split(",", 3)[3]
        for line in completed.stdout.splitlines()
        if len(line.split(",", 3)) == 4 and line.split(",", 3)[2] == "state"
    ]
    if len(states) != 1 or states[0] not in HALTED_STATES:
        raise RuntimeError(f"Prepared {role} image must be halted, found {states}")


def package_role(role: Role, output_dir: Path) -> Path:
    """Flatten one role overlay and write an isolated, local-only box archive."""
    _require_halted(role)
    source_disk = _role_disk(role)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"sticks-c0045-{role}-arm64.box"
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite prepared role box: {output_path}")
    with tempfile.TemporaryDirectory(prefix=f"sticks-{role}-", dir=output_dir) as raw_staging:
        staging = Path(raw_staging)
        image_path = staging / "box.img"
        subprocess.run(
            ["qemu-img", "convert", "-O", "qcow2", str(source_disk), str(image_path)],
            check=True,
        )
        (staging / "metadata.json").write_text(
            json.dumps({"format": "qcow2", "provider": "libvirt"}) + "\n",
            encoding="utf-8",
        )
        (staging / "Vagrantfile").write_text("Vagrant.configure('2') do |config|\nend\n", encoding="utf-8")
        staged_archive = staging / output_path.name
        with tarfile.open(staged_archive, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            for name in ("metadata.json", "Vagrantfile", "box.img"):
                archive.add(staging / name, arcname=name, recursive=False)
        staged_archive.replace(output_path)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=ROLES, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    options = parser.parse_args()
    print(package_role(options.role, options.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
