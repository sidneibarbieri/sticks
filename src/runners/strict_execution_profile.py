"""Typed, fail-closed contract for the C0045 strict execution mode."""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from runners.capability_facts import Digest, Identity, ImmutableRecord

ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_V10_PATH = ARTIFACT_ROOT / "data/experiments/c0045_strict_execution_profile_v10.json"
PROFILE_V9_PATH = ARTIFACT_ROOT / "data/experiments/c0045_strict_execution_profile_v9.json"
PROFILE_V8_PATH = ARTIFACT_ROOT / "data/experiments/c0045_strict_execution_profile_v8.json"
PROFILE_V7_PATH = ARTIFACT_ROOT / "data/experiments/c0045_strict_execution_profile_v7.json"
PROFILE_NAME_PATTERN = re.compile(r"c0045_strict_execution_profile_v([1-9]\d*)\.json")
PROFILE_SCHEMA_PATTERN = re.compile(r"c0045-strict-execution-profile/v([1-9]\d*)")
PREPARED_RUNTIME_MANIFEST_NAME_PATTERN = re.compile(
    r"c0045_prepared_runtime_manifest_v([1-9]\d*)\.json"
)
PREPARED_RUNTIME_MANIFEST_SCHEMA_PATTERN = re.compile(
    r"c0045-prepared-runtime-manifest/v([1-9]\d*)"
)
PREPARED_RUNTIME_MANIFEST_RELATIVE_PATH = (
    "data/experiments/c0045_prepared_runtime_manifest_v5.json"
)
RETIRED_PROFILE_PATHS = (
    ARTIFACT_ROOT / "data/experiments/c0045_strict_execution_profile_v6.json",
    ARTIFACT_ROOT / "data/experiments/c0045_strict_execution_profile_v5.json",
    ARTIFACT_ROOT / "data/experiments/c0045_strict_execution_profile_v4.json",
    ARTIFACT_ROOT / "data/experiments/c0045_strict_execution_profile_v3.json",
    ARTIFACT_ROOT / "data/experiments/c0045_strict_execution_profile_v2.json",
)
LEGACY_PROFILE_PATH = (
    ARTIFACT_ROOT / "data/experiments/c0045_strict_execution_profile_v1.json"
)
REQUIREMENTS_LOCK_PATH = ARTIFACT_ROOT / "requirements.lock"
SERIES_PATH = ARTIFACT_ROOT / "data/experiments/c0045_compute_effect_series_v1.json"
SERIES_PATH_PATTERN = re.compile(
    r"data/experiments/c0045_compute_effect_series_v([1-9]\d*)\.json"
)
STUDY_PATH = ARTIFACT_ROOT / "data/experiments/c0045_compute_effect_v1.json"
LAB_ROOT = ARTIFACT_ROOT / "lab/vagrant"
LEGACY_STRICT_EXECUTION_SOURCE_PATHS = (
    Path("src"),
    Path("scripts"),
    Path("lab/health_check.py"),
)
STRICT_EXECUTION_ENTRYPOINTS = (
    Path("scripts/run_strict_c0045_effect_series.py"),
    Path("scripts/preflight_strict_c0045.py"),
    Path("scripts/run_c0045_effect_series.py"),
    Path("scripts/run_c0045_effect_series_cell.py"),
    Path("scripts/up_lab.sh"),
    Path("scripts/destroy_lab.sh"),
    Path("apply_sut_profile.py"),
    Path("lab/health_check.py"),
)
class StrictExecutionProfile(ImmutableRecord):
    """Immutable source and runtime requirements for live C0045 collection."""

    schema_version: str
    mode: Literal["strict_experiment"]
    provider: Literal["qemu"]
    minimum_vagrant_qemu_version: str
    requirements_lock_sha256: Digest
    series_path: Identity = "data/experiments/c0045_compute_effect_series_v1.json"
    series_sha256: Digest
    study_sha256: Digest
    vagrantfile_sha256: dict[Literal["caldera", "attacker", "target-linux-1"], Digest]
    provisioning_input_sha256: dict[str, Digest]
    prepared_runtime_manifest_path: Identity = PREPARED_RUNTIME_MANIFEST_RELATIVE_PATH
    prepared_runtime_manifest_sha256: Digest
    execution_source_sha256: Digest
    execution_source_paths: tuple[Identity, ...] = ()

    @field_validator("schema_version")
    @classmethod
    def require_supported_schema_version(cls, value: str) -> str:
        match = PROFILE_SCHEMA_PATTERN.fullmatch(value)
        if match is None or int(match.group(1)) < 7:
            raise ValueError("Strict C0045 profile schema must be v7 or newer")
        return value

    @model_validator(mode="after")
    def require_complete_topology(self) -> Self:
        if set(self.vagrantfile_sha256) != {"caldera", "attacker", "target-linux-1"}:
            raise ValueError("Strict C0045 profile must bind every managed VM")
        return self

    @model_validator(mode="after")
    def require_provisioning_inputs(self) -> Self:
        if not self.provisioning_input_sha256:
            raise ValueError("Strict C0045 profile must bind every provisioning input")
        return self

    @model_validator(mode="after")
    def require_v8_source_inventory(self) -> Self:
        if strict_profile_version(self.schema_version) >= 8 and not self.execution_source_paths:
            raise ValueError("Strict C0045 v8+ profile must list execution sources")
        if self.schema_version == "c0045-strict-execution-profile/v7" and self.execution_source_paths:
            raise ValueError("Strict C0045 v7 profile cannot declare a v8 source inventory")
        return self

    @field_validator("prepared_runtime_manifest_path")
    @classmethod
    def require_canonical_prepared_runtime_manifest_path(cls, value: str) -> str:
        """Keep each profile bound to one manifest below the artifact tree."""
        expected_prefix = "data/experiments/"
        if (
            not value.startswith(expected_prefix)
            or "\\" in value
            or ":" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError("Prepared runtime manifest path must be canonical")
        if PREPARED_RUNTIME_MANIFEST_NAME_PATTERN.fullmatch(value.rsplit("/", 1)[-1]) is None:
            raise ValueError("Prepared runtime manifest path must name a versioned manifest")
        return value

    @field_validator("series_path")
    @classmethod
    def require_declared_series_path(cls, value: str) -> str:
        """Bind strict execution to one versioned, artifact-local schedule."""
        if SERIES_PATH_PATTERN.fullmatch(value) is None:
            raise ValueError("Strict C0045 series path must name a frozen schedule")
        return value

    @model_validator(mode="after")
    def require_new_profiles_to_bind_a_nonlegacy_manifest(self) -> Self:
        if (
            strict_profile_version(self.schema_version) >= 12
            and self.prepared_runtime_manifest_path
            == PREPARED_RUNTIME_MANIFEST_RELATIVE_PATH
        ):
            raise ValueError("Strict C0045 v12+ profile must declare its prepared manifest")
        return self

    @model_validator(mode="after")
    def require_v21_series_binding(self) -> Self:
        if (
            strict_profile_version(self.schema_version) >= 21
            and self.series_path == "data/experiments/c0045_compute_effect_series_v1.json"
        ):
            raise ValueError("Strict C0045 v21+ profile must bind its series revision")
        return self


class PreparedRuntimeManifest(ImmutableRecord):
    """Attest an offline C0045 runtime before it may enter strict collection."""

    schema_version: str
    images: dict[
        Literal["caldera", "attacker", "target-linux-1"], PreparedRuntimeImage
    ]
    provisioning_input_sha256: dict[str, Digest]

    @field_validator("schema_version")
    @classmethod
    def require_supported_schema_version(cls, value: str) -> str:
        match = PREPARED_RUNTIME_MANIFEST_SCHEMA_PATTERN.fullmatch(value)
        if match is None or int(match.group(1)) < 3:
            raise ValueError("Prepared C0045 runtime manifest schema must be v3 or newer")
        return value

    @model_validator(mode="after")
    def require_complete_provisioning_inventory(self) -> Self:
        if not self.provisioning_input_sha256:
            raise ValueError(
                "Prepared C0045 runtime manifest must bind every provisioning input"
            )
        return self

    @model_validator(mode="after")
    def require_complete_image_topology(self) -> Self:
        if set(self.images) != {"caldera", "attacker", "target-linux-1"}:
            raise ValueError("Prepared C0045 runtime must bind every managed VM image")
        return self

    @model_validator(mode="after")
    def require_plugin_box_format(self) -> Self:
        version = int(self.schema_version.rsplit("v", 1)[1])
        if version >= 8 and any(
            image.box_provider != "libvirt" for image in self.images.values()
        ):
            raise ValueError("Prepared C0045 v8+ images require libvirt box format")
        return self


class PreparedRuntimeImage(ImmutableRecord):
    """One immutable, role-specific VM image for strict C0045 execution."""

    box_name: Identity
    box_version: Identity
    box_provider: Literal["qemu", "libvirt"] = "qemu"
    image_fingerprint_sha256: Digest
    guest_inventory_sha256: Digest


class StrictExecutionReceipt(ImmutableRecord):
    """Non-scientific receipt proving that live collection was preflighted."""

    schema_version: Literal["c0045-strict-preflight-receipt/v2"]
    profile_sha256: Digest
    requirements_lock_sha256: Digest
    prepared_runtime_manifest_sha256: Digest
    image_fingerprint_sha256: Digest
    vagrant_version: str = Field(min_length=1)
    vagrant_qemu_version: str = Field(min_length=1)
    box_providers: dict[
        Literal["caldera", "attacker", "target-linux-1"], Literal["qemu", "libvirt"]
    ]
    socket_path: str = Field(min_length=1)


def sha256_file(path: Path) -> str:
    """Return the content digest of one regular source or image file."""
    if not path.is_file():
        raise FileNotFoundError(f"Required strict-mode input is absent: {path}")
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def strict_profile_version(schema_version: str) -> int:
    """Return the numeric revision from a validated strict profile schema."""
    match = PROFILE_SCHEMA_PATTERN.fullmatch(schema_version)
    if match is None:
        raise ValueError(f"Unsupported strict execution profile schema: {schema_version}")
    return int(match.group(1))


def latest_strict_profile_path() -> Path | None:
    """Return the newest immutable strict profile, ignoring retired revisions."""
    profiles: list[tuple[int, Path]] = []
    for path in (ARTIFACT_ROOT / "data/experiments").glob(
        "c0045_strict_execution_profile_v*.json"
    ):
        match = PROFILE_NAME_PATTERN.fullmatch(path.name)
        if match is not None and int(match.group(1)) >= 7:
            profiles.append((int(match.group(1)), path))
    return max(profiles, default=(0, None), key=lambda item: item[0])[1]


def next_strict_profile_path() -> tuple[int, Path]:
    """Reserve the next immutable profile pathname without replacing any record."""
    current = latest_strict_profile_path()
    current_version = (
        int(PROFILE_NAME_PATTERN.fullmatch(current.name).group(1))
        if current is not None
        else 6
    )
    next_version = current_version + 1
    return (
        next_version,
        ARTIFACT_ROOT
        / "data/experiments"
        / f"c0045_strict_execution_profile_v{next_version}.json",
    )


def latest_prepared_runtime_manifest_path() -> Path | None:
    """Return the newest immutable prepared-runtime manifest."""
    manifests: list[tuple[int, Path]] = []
    for path in (ARTIFACT_ROOT / "data/experiments").glob(
        "c0045_prepared_runtime_manifest_v*.json"
    ):
        match = PREPARED_RUNTIME_MANIFEST_NAME_PATTERN.fullmatch(path.name)
        if match is not None:
            manifests.append((int(match.group(1)), path))
    return max(manifests, default=(0, None), key=lambda item: item[0])[1]


def next_prepared_runtime_manifest_path() -> tuple[int, Path]:
    """Reserve the next manifest pathname without replacing an immutable record."""
    current = latest_prepared_runtime_manifest_path()
    current_version = (
        int(PREPARED_RUNTIME_MANIFEST_NAME_PATTERN.fullmatch(current.name).group(1))
        if current is not None
        else 0
    )
    next_version = current_version + 1
    return (
        next_version,
        ARTIFACT_ROOT
        / "data/experiments"
        / f"c0045_prepared_runtime_manifest_v{next_version}.json",
    )


def prepared_runtime_manifest_path(profile: StrictExecutionProfile) -> Path:
    """Resolve the manifest explicitly declared by one frozen profile."""
    path = ARTIFACT_ROOT / profile.prepared_runtime_manifest_path
    if path.parent != ARTIFACT_ROOT / "data/experiments":
        raise ValueError("Prepared C0045 runtime manifest escapes the artifact root")
    return path


def _source_tree_paths(relative_roots: tuple[Path, ...]) -> tuple[Path, ...]:
    """Return regular Python and shell sources below declared legacy roots."""
    files: list[Path] = []
    for relative_root in relative_roots:
        root = ARTIFACT_ROOT / relative_root
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix in {".py", ".sh"}
            )
        else:
            raise FileNotFoundError(f"Required strict execution source is absent: {root}")
    return tuple(sorted(set(files)))


def _module_source(module_name: str) -> Path | None:
    """Resolve one first-party import under the artifact's declared Python roots."""
    parts = module_name.split(".")
    for source_root in (ARTIFACT_ROOT / "src", ARTIFACT_ROOT):
        module_path = source_root.joinpath(*parts).with_suffix(".py")
        package_path = source_root.joinpath(*parts) / "__init__.py"
        if module_path.is_file():
            return module_path
        if package_path.is_file():
            return package_path
    return None


def _first_party_imports(path: Path) -> tuple[Path, ...]:
    """Resolve direct local Python imports without treating third-party code as source."""
    if path.suffix != ".py":
        return ()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    dependencies: set[Path] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            module_names = (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            module_names = (node.module,)
        else:
            continue
        for module_name in module_names:
            source = _module_source(module_name)
            if source is not None:
                dependencies.add(source)
    return tuple(sorted(dependencies))


def strict_execution_dependency_paths() -> tuple[Path, ...]:
    """Return the transitive, execution-relevant source closure for strict v8."""
    pending = list(_source_tree_paths(STRICT_EXECUTION_ENTRYPOINTS))
    resolved: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in resolved:
            continue
        resolved.add(path)
        pending.extend(
            dependency
            for dependency in _first_party_imports(path)
            if dependency not in resolved
        )
    return tuple(sorted(resolved))


def strict_execution_dependency_relative_paths() -> tuple[str, ...]:
    """Return v8's reviewable source inventory in deterministic order."""
    return tuple(
        path.relative_to(ARTIFACT_ROOT).as_posix()
        for path in strict_execution_dependency_paths()
    )


def _fingerprint_sources(paths: tuple[Path, ...]) -> str:
    """Hash source bytes together with their artifact-relative identities."""
    digest = hashlib.sha256()
    for path in paths:
        relative_path = path.relative_to(ARTIFACT_ROOT).as_posix().encode("utf-8")
        digest.update(len(relative_path).to_bytes(8, "big"))
        digest.update(relative_path)
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def strict_execution_source_sha256(
    schema_version: str = "c0045-strict-execution-profile/v7",
) -> str:
    """Fingerprint the execution closure selected by the profile schema version."""
    if schema_version == "c0045-strict-execution-profile/v7":
        return _fingerprint_sources(_source_tree_paths(LEGACY_STRICT_EXECUTION_SOURCE_PATHS))
    if strict_profile_version(schema_version) >= 8:
        return _fingerprint_sources(strict_execution_dependency_paths())
    raise ValueError(f"Unsupported strict execution profile schema: {schema_version}")


def load_prepared_runtime_manifest(
    profile: StrictExecutionProfile,
) -> PreparedRuntimeManifest:
    """Load the prepared image attestation and bind it to its strict profile."""
    manifest_path = prepared_runtime_manifest_path(profile)
    if sha256_file(manifest_path) != profile.prepared_runtime_manifest_sha256:
        raise ValueError("Prepared C0045 runtime manifest differs from strict profile")
    manifest = PreparedRuntimeManifest.model_validate_json(
        manifest_path.read_bytes()
    )
    if manifest.provisioning_input_sha256 != profile.provisioning_input_sha256:
        raise ValueError("Prepared C0045 runtime inputs differ from strict profile")
    return manifest


def strict_prepared_environment(manifest: PreparedRuntimeManifest) -> dict[str, str]:
    """Return the complete role-to-box mapping consumed by strict Vagrantfiles."""
    return {
        "STICKS_STRICT_PREPARED": "1",
        "STICKS_STRICT_BOX_CALDERA": manifest.images["caldera"].box_name,
        "STICKS_STRICT_BOX_VERSION_CALDERA": manifest.images["caldera"].box_version,
        "STICKS_STRICT_BOX_ATTACKER": manifest.images["attacker"].box_name,
        "STICKS_STRICT_BOX_VERSION_ATTACKER": manifest.images["attacker"].box_version,
        "STICKS_STRICT_BOX_TARGET": manifest.images["target-linux-1"].box_name,
        "STICKS_STRICT_BOX_VERSION_TARGET": manifest.images[
            "target-linux-1"
        ].box_version,
    }


def load_strict_execution_profile() -> StrictExecutionProfile:
    """Load the frozen profile and reject any source drift before a boot."""
    profile_path = latest_strict_profile_path()
    if not profile_path.is_file():
        if any(path.is_file() for path in RETIRED_PROFILE_PATHS):
            raise RuntimeError(
                "Strict C0045 v2-v6 profiles are retired: their prepared images or "
                "execution source bindings predate the current runtime. Freeze a v8 "
                "runtime before collection."
            )
        if LEGACY_PROFILE_PATH.is_file():
            raise RuntimeError(
                "Strict C0045 v1 is retired: it permitted online guest provisioning. "
                "Build and attest a prepared offline runtime, then freeze a v8 profile."
            )
        raise FileNotFoundError("Strict C0045 v7/v8 profile is absent")
    profile = StrictExecutionProfile.model_validate_json(profile_path.read_bytes())
    required_digests = {
        REQUIREMENTS_LOCK_PATH: profile.requirements_lock_sha256,
        ARTIFACT_ROOT / profile.series_path: profile.series_sha256,
        STUDY_PATH: profile.study_sha256,
        **{
            LAB_ROOT / vm_name / "Vagrantfile": digest
            for vm_name, digest in profile.vagrantfile_sha256.items()
        },
        **{
            ARTIFACT_ROOT / relative_path: digest
            for relative_path, digest in profile.provisioning_input_sha256.items()
        },
    }
    for path, expected in required_digests.items():
        if sha256_file(path) != expected:
            raise ValueError(
                f"Strict C0045 source differs from its frozen profile: {path}"
            )
    if strict_profile_version(profile.schema_version) >= 8 and (
        profile.execution_source_paths != strict_execution_dependency_relative_paths()
    ):
        raise ValueError("Strict C0045 v8 execution source inventory differs from profile")
    if strict_execution_source_sha256(profile.schema_version) != profile.execution_source_sha256:
        raise ValueError("Strict C0045 execution source differs from its frozen profile")
    load_prepared_runtime_manifest(profile)
    return profile


def strict_profile_sha256() -> str:
    """Return the frozen profile identity used in a preflight receipt."""
    profile_path = latest_strict_profile_path()
    if profile_path is None:
        raise FileNotFoundError("Strict C0045 v7 or newer profile is absent")
    return sha256_file(profile_path)


def image_tree_sha256(image_root: Path) -> str:
    """Fingerprint every regular image file without following links."""
    if not image_root.is_dir():
        raise FileNotFoundError(f"Pinned Vagrant box is absent: {image_root}")
    digest = hashlib.sha256()
    files = sorted(path for path in image_root.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"Pinned Vagrant box contains no regular files: {image_root}")
    for path in files:
        relative_path = path.relative_to(image_root).as_posix().encode("utf-8")
        digest.update(len(relative_path).to_bytes(8, "big"))
        digest.update(relative_path)
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()
