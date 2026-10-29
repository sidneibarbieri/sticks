"""Freeze prepared C0045 role images into the next immutable strict contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(PROJECT_ROOT / "src"), str(PROJECT_ROOT))

from runners.prepared_runtime_attestation import PreparedGuestInventory  # noqa: E402
from runners.prepared_image_provenance import require_image_provenance  # noqa: E402
from runners.c0045_effect_series import SERIES_PATHS  # noqa: E402
from runners.strict_execution_profile import (  # noqa: E402
    LAB_ROOT,
    REQUIREMENTS_LOCK_PATH,
    STUDY_PATH,
    PreparedRuntimeImage,
    PreparedRuntimeManifest,
    StrictExecutionProfile,
    image_tree_sha256,
    sha256_file,
    strict_execution_dependency_relative_paths,
    strict_execution_source_sha256,
    latest_strict_profile_path,
    latest_prepared_runtime_manifest_path,
    next_prepared_runtime_manifest_path,
    next_strict_profile_path,
    strict_profile_version,
)

Role = Literal["caldera", "attacker", "target-linux-1"]
ROLES: tuple[Role, ...] = ("caldera", "attacker", "target-linux-1")
ROLE_BOX_NAMES: dict[Role, str] = {
    "caldera": "sticks/c0045-v10-caldera-arm64",
    "attacker": "sticks/c0045-v10-attacker-arm64",
    "target-linux-1": "sticks/c0045-v10-target-linux-1-arm64",
}
BOX_VERSION = "0"
BOX_PROVIDER = "libvirt"
MINIMUM_VAGRANT_QEMU_VERSION = "0.6.3"
PROVISIONING_INPUTS = (
    "lab/vagrant/shared/apt_guard.sh",
    "lab/vagrant/shared/base.sh",
    "lab/vagrant/shared/attacker.sh",
    "lab/vagrant/shared/caldera.sh",
    "lab/vagrant/shared/target.sh",
    "lab/vagrant/shared/caldera-runtime-requirements.txt",
    "lab/vagrant/shared/qemu_network_yaml.rb",
    "lab/vagrant/shared/qemu_ssh_port.rb",
    "lab/vagrant/shared/prepare_strict_ssh.sh",
    "lab/vagrant/apply_sut_profile.py",
    "campaigns/0.shadowray.json",
    "data/sut_profiles/0.shadowray.yml",
)


def _box_root(box_name: str) -> Path:
    """Resolve the declared local Vagrant image instead of assuming its alias."""
    vagrant_home = Path(os.environ.get("VAGRANT_HOME", "~/.vagrant.d")).expanduser()
    return (
        vagrant_home
        / "boxes"
        / box_name.replace("/", "-VAGRANTSLASH-")
        / BOX_VERSION
        / "arm64"
        / BOX_PROVIDER
    )


def _inventory_path(inventory_dir: Path, role: Role) -> Path:
    return inventory_dir / f"c0045-{role}-prepared-guest-inventory-v1.json"


def _provisioning_digests() -> dict[str, str]:
    return {relative: sha256_file(PROJECT_ROOT / relative) for relative in PROVISIONING_INPUTS}


def _frozen_series_path(series_path: Path) -> Path:
    """Resolve and accept only a declared immutable C0045 schedule."""
    resolved = series_path.resolve()
    if resolved not in SERIES_PATHS:
        raise ValueError("Strict C0045 profile requires a declared frozen schedule")
    return resolved


def _prepared_manifest(
    inventory_dir: Path, manifest_version: int
) -> PreparedRuntimeManifest:
    images: dict[Role, PreparedRuntimeImage] = {}
    for role in ROLES:
        inventory_path = _inventory_path(inventory_dir, role)
        PreparedGuestInventory.model_validate_json(inventory_path.read_bytes())
        box_name = ROLE_BOX_NAMES[role]
        images[role] = PreparedRuntimeImage(
            box_name=box_name,
            box_version=BOX_VERSION,
            box_provider=BOX_PROVIDER,
            image_fingerprint_sha256=image_tree_sha256(_box_root(box_name)),
            guest_inventory_sha256=sha256_file(inventory_path),
        )
    return PreparedRuntimeManifest(
        schema_version=f"c0045-prepared-runtime-manifest/v{manifest_version}",
        images=images,
        provisioning_input_sha256=_provisioning_digests(),
    )


def _strict_profile(
    manifest: PreparedRuntimeManifest,
    manifest_path: Path,
    profile_version: int,
    series_path: Path = PROJECT_ROOT / "data/experiments/c0045_compute_effect_series_v1.json",
) -> StrictExecutionProfile:
    series_path = _frozen_series_path(series_path)
    return StrictExecutionProfile(
        schema_version=f"c0045-strict-execution-profile/v{profile_version}",
        mode="strict_experiment",
        provider="qemu",
        minimum_vagrant_qemu_version=MINIMUM_VAGRANT_QEMU_VERSION,
        requirements_lock_sha256=sha256_file(REQUIREMENTS_LOCK_PATH),
        series_path=series_path.relative_to(PROJECT_ROOT).as_posix(),
        series_sha256=sha256_file(series_path),
        study_sha256=sha256_file(STUDY_PATH),
        vagrantfile_sha256={
            role: sha256_file(LAB_ROOT / role / "Vagrantfile") for role in ROLES
        },
        provisioning_input_sha256=manifest.provisioning_input_sha256,
        prepared_runtime_manifest_path=manifest_path.relative_to(PROJECT_ROOT).as_posix(),
        execution_source_sha256=strict_execution_source_sha256(
            f"c0045-strict-execution-profile/v{profile_version}"
        ),
        execution_source_paths=strict_execution_dependency_relative_paths(),
        prepared_runtime_manifest_sha256=hashlib.sha256(
            manifest.model_dump_json(indent=2).encode("utf-8") + b"\n"
        ).hexdigest(),
    )


def _same_prepared_runtime(
    candidate: PreparedRuntimeManifest, existing: PreparedRuntimeManifest
) -> bool:
    """Compare immutable runtime content while ignoring the record revision."""
    return (
        candidate.images == existing.images
        and candidate.provisioning_input_sha256 == existing.provisioning_input_sha256
    )


def _require_image_provenance(
    candidate: PreparedRuntimeManifest, existing: PreparedRuntimeManifest
) -> None:
    require_image_provenance(
        existing.provisioning_input_sha256,
        candidate.provisioning_input_sha256,
        {role: image.image_fingerprint_sha256 for role, image in existing.images.items()},
        {role: image.image_fingerprint_sha256 for role, image in candidate.images.items()},
    )


def _write_immutable(path: Path, content: str) -> None:
    """Write a new frozen record atomically; reject replacement or drift."""
    payload = content.encode("utf-8")
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"Frozen strict record already differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sticks-freeze-", dir=path.parent) as raw_staging:
        staged_path = Path(raw_staging) / path.name
        staged_path.write_bytes(payload)
        staged_path.replace(path)


def freeze(
    inventory_dir: Path,
    series_path: Path = PROJECT_ROOT / "data/experiments/c0045_compute_effect_series_v1.json",
) -> tuple[PreparedRuntimeManifest, StrictExecutionProfile, Path]:
    """Create the matching manifest and strict profile from current verified inputs."""
    latest_manifest_path = latest_prepared_runtime_manifest_path()
    if latest_manifest_path is not None:
        latest_manifest = PreparedRuntimeManifest.model_validate_json(
            latest_manifest_path.read_bytes()
        )
        candidate = _prepared_manifest(
            inventory_dir,
            int(latest_manifest.schema_version.rsplit("v", 1)[1]),
        )
        _require_image_provenance(candidate, latest_manifest)
        if _same_prepared_runtime(candidate, latest_manifest):
            manifest = latest_manifest
            manifest_path = latest_manifest_path
        else:
            manifest_version, manifest_path = next_prepared_runtime_manifest_path()
            manifest = _prepared_manifest(inventory_dir, manifest_version)
            _write_immutable(manifest_path, manifest.model_dump_json(indent=2) + "\n")
    else:
        manifest_version, manifest_path = next_prepared_runtime_manifest_path()
        manifest = _prepared_manifest(inventory_dir, manifest_version)
        _write_immutable(manifest_path, manifest.model_dump_json(indent=2) + "\n")
    latest_profile_path = latest_strict_profile_path()
    if latest_profile_path is not None:
        latest_profile = StrictExecutionProfile.model_validate_json(
            latest_profile_path.read_bytes()
        )
        current_profile = _strict_profile(
            manifest,
            manifest_path,
            strict_profile_version(latest_profile.schema_version),
            series_path,
        )
        if current_profile == latest_profile:
            return manifest, latest_profile, latest_profile_path
    profile_version, profile_path = next_strict_profile_path()
    profile = _strict_profile(manifest, manifest_path, profile_version, series_path)
    _write_immutable(profile_path, profile.model_dump_json(indent=2) + "\n")
    return manifest, profile, profile_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-dir", required=True, type=Path)
    parser.add_argument(
        "--series-path",
        type=Path,
        default=PROJECT_ROOT / "data/experiments/c0045_compute_effect_series_v1.json",
    )
    options = parser.parse_args()
    manifest, profile, profile_path = freeze(
        options.inventory_dir, options.series_path
    )
    print(
        json.dumps(
            {
            "manifest": str(
                latest_prepared_runtime_manifest_path()
                if latest_prepared_runtime_manifest_path() is not None
                else ""
            ),
            "profile": str(profile_path),
            "roles": sorted(manifest.images),
            "profile_sha256": hashlib.sha256(
                profile.model_dump_json(indent=2).encode("utf-8") + b"\n"
            ).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
