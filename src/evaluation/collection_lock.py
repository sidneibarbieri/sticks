"""Bind a prospective comparison cache to its declared inputs and source revision."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from concretization.models import StrictModel

LOCK_FILENAME = "collection-lock.json"
FROZEN_SOURCE_DIRECTORY = "frozen-source"
FROZEN_SOURCE_MANIFEST_FILENAME = "frozen-source-manifest.json"
SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
EXECUTION_INPUT_DIRECTORIES = (
    "scripts",
    "lab",
    "data/runtime_contracts",
    "data/observer_specs",
    "data/campaigns",
    "data/sut_profiles",
    "data/campaign_objectives",
    "data/experiments",
    "data/suts",
    "data/interop",
    "data/concretization",
)
EXECUTION_INPUT_SUFFIXES = frozenset(
    {".py", ".sh", ".rb", ".json", ".yaml", ".yml", ".txt"}
)


class CollectionLock(StrictModel):
    schema_version: Literal[1, 2, 3, 4] = 1
    experiment_id: str
    model: str
    ollama_model_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temperature: float
    top_p: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False)
    runtime_id: str | None = Field(default=None, min_length=1)
    thinking_mode: bool | str
    max_output_tokens: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    retry_limit: int = Field(gt=0)
    campaigns: list[str]
    seeds: list[int]
    shuffle_seed: int
    source_sha256: dict[str, str]
    source_tree_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_runtime_metadata(self) -> "CollectionLock":
        if self.schema_version >= 2 and (self.top_p is None or self.runtime_id is None):
            raise ValueError("schema 2 or newer requires explicit top_p and runtime_id")
        if self.schema_version == 1 and (
            self.top_p is not None or self.runtime_id is not None
        ):
            raise ValueError("runtime metadata requires schema 2")
        if self.schema_version >= 4 and self.source_tree_sha256 is None:
            raise ValueError("schema 4 requires a frozen source-tree digest")
        if self.schema_version < 4 and self.source_tree_sha256 is not None:
            raise ValueError("frozen source-tree digest requires schema 4")
        return self


def execution_input_paths(project_root: Path) -> list[Path]:
    """Pin runtime specifications, guest probes, provisioning and dependencies."""
    paths = [project_root / "requirements.txt", project_root / "requirements.lock"]
    for relative_directory in EXECUTION_INPUT_DIRECTORIES:
        directory = project_root / relative_directory
        if not directory.is_dir():
            raise FileNotFoundError(
                f"Missing execution input directory: {relative_directory}"
            )
        paths.extend(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and not any(
                part.startswith(".") or part == "__pycache__"
                for part in path.relative_to(directory).parts
            )
            and (path.suffix in EXECUTION_INPUT_SUFFIXES or path.name == "Vagrantfile")
        )
    return sorted(set(paths))


def _safe_identifier(value: str, label: str) -> None:
    if SAFE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a simple identifier: {value!r}")


def source_tree_sha256(source_hashes: dict[str, str]) -> str:
    """Hash the canonical source map before copying it into a collection."""
    return hashlib.sha256(
        json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_collection_lock(
    project_root: Path,
    *,
    experiment_id: str,
    model: str,
    ollama_model_digest: str,
    temperature: float,
    thinking_mode: bool | str,
    max_output_tokens: int,
    timeout_seconds: int,
    retry_limit: int,
    campaigns: list[str],
    seeds: list[int],
    shuffle_seed: int,
    top_p: float | None = None,
    runtime_id: str | None = None,
    schema_version: Literal[1, 2, 3] | None = None,
) -> CollectionLock:
    """Hash every selected campaign input and the collector's Python source tree."""
    _safe_identifier(experiment_id, "experiment_id")
    if not campaigns or len(set(campaigns)) != len(campaigns):
        raise ValueError("campaigns must be nonempty and unique")
    for campaign in campaigns:
        _safe_identifier(campaign, "campaign")
    if not model or SHA256_HEX.fullmatch(ollama_model_digest) is None:
        raise ValueError("a model tag and Ollama model digest are required")
    if not math.isfinite(temperature) or temperature < 0:
        raise ValueError("temperature must be finite and nonnegative")
    if isinstance(thinking_mode, str) and not thinking_mode:
        raise ValueError("thinking mode must be explicit")
    if min(max_output_tokens, timeout_seconds, retry_limit) <= 0:
        raise ValueError("generation budget and retry limits must be positive")
    if len(seeds) < 5 or len(set(seeds)) != len(seeds):
        raise ValueError("at least five distinct seeds are required")

    version = schema_version or (
        4 if top_p is not None or runtime_id is not None else 1
    )
    source_paths = sorted((project_root / "src").rglob("*.py"))
    if version >= 3:
        source_paths.extend(execution_input_paths(project_root))
    source_paths.extend(
        project_root / "scripts" / script
        for script in (
            "collect_controlled_comparison.py",
            "analyze_controlled_comparison.py",
        )
    )
    source_paths.append(project_root / "data/concretization/action_templates.json")
    for campaign in campaigns:
        source_paths.extend(
            project_root / "release/plans" / f"{campaign}.{suffix}.json"
            for suffix in ("procedural-plan", "concretized-plan", "binding-catalog")
        )
    source_hashes = {
        path.relative_to(project_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in source_paths
    }
    return CollectionLock(
        schema_version=version,
        experiment_id=experiment_id,
        model=model,
        ollama_model_digest=ollama_model_digest,
        temperature=temperature,
        top_p=top_p,
        runtime_id=runtime_id,
        thinking_mode=thinking_mode,
        max_output_tokens=max_output_tokens,
        timeout_seconds=timeout_seconds,
        retry_limit=retry_limit,
        campaigns=campaigns,
        seeds=seeds,
        shuffle_seed=shuffle_seed,
        source_sha256=source_hashes,
        source_tree_sha256=source_tree_sha256(source_hashes) if version >= 4 else None,
    )


def freeze_collection_sources(
    project_root: Path, directory: Path, lock: CollectionLock
) -> Path:
    """Seal every locked input so a later source edit cannot erase provenance."""
    if lock.schema_version < 4:
        raise ValueError("only collection schema 4 or newer carries a source snapshot")
    snapshot_directory = directory / FROZEN_SOURCE_DIRECTORY
    manifest_path = directory / FROZEN_SOURCE_MANIFEST_FILENAME
    if snapshot_directory.exists() or manifest_path.exists():
        raise FileExistsError("collection already contains a frozen source snapshot")

    snapshot_directory.mkdir()
    try:
        for relative_path, expected_hash in lock.source_sha256.items():
            source_path = project_root / relative_path
            actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                raise ValueError(f"source changed before snapshot: {relative_path}")
            destination = snapshot_directory / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination)
        manifest = {
            "schema_version": 1,
            "source_tree_sha256": lock.source_tree_sha256,
            "source_sha256": lock.source_sha256,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    except Exception:
        shutil.rmtree(snapshot_directory, ignore_errors=True)
        manifest_path.unlink(missing_ok=True)
        raise
    return manifest_path


def verify_frozen_collection_sources(directory: Path, lock: CollectionLock) -> Path:
    """Verify that the sealed source tree still exactly matches the collection lock."""
    if lock.schema_version < 4:
        raise ValueError("collection schema has no frozen source snapshot")
    manifest_path = directory / FROZEN_SOURCE_MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise ValueError(f"collection has no frozen source snapshot: {directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest != {
        "schema_version": 1,
        "source_tree_sha256": lock.source_tree_sha256,
        "source_sha256": lock.source_sha256,
    }:
        raise ValueError(
            f"frozen source manifest differs from collection lock: {manifest_path}"
        )
    if source_tree_sha256(lock.source_sha256) != lock.source_tree_sha256:
        raise ValueError(f"invalid frozen source-tree digest: {manifest_path}")
    snapshot_directory = directory / FROZEN_SOURCE_DIRECTORY
    for relative_path, expected_hash in lock.source_sha256.items():
        snapshot_path = snapshot_directory / relative_path
        if not snapshot_path.is_file():
            raise ValueError(f"frozen source is missing: {relative_path}")
        actual_hash = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(
                f"frozen source differs from collection lock: {relative_path}"
            )
    return manifest_path


def prepare_collection_directory(
    directory: Path, expected: CollectionLock, *, project_root: Path | None = None
) -> Path:
    """Create a lock before collection or reject incompatible and legacy caches."""
    lock_path = directory / LOCK_FILENAME
    if lock_path.exists():
        existing = CollectionLock.model_validate_json(
            lock_path.read_text(encoding="utf-8")
        )
        if existing != expected:
            raise ValueError(f"collection inputs differ from frozen lock: {lock_path}")
        return lock_path
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"existing collection has no frozen lock: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    if expected.schema_version >= 4:
        if project_root is None:
            raise ValueError("schema 4 collection requires the source project root")
        freeze_collection_sources(project_root, directory, expected)
    with lock_path.open("x", encoding="utf-8") as output:
        json.dump(expected.model_dump(mode="json"), output, indent=2, sort_keys=True)
        output.write("\n")
    return lock_path


def verify_collection_sources(project_root: Path, directory: Path) -> CollectionLock:
    """Reject analysis under source bytes other than those frozen for collection."""
    lock_path = directory / LOCK_FILENAME
    if not lock_path.is_file():
        raise ValueError(f"collection has no frozen source lock: {directory}")
    locked = CollectionLock.model_validate_json(lock_path.read_text(encoding="utf-8"))
    if locked.schema_version >= 4:
        verify_frozen_collection_sources(directory, locked)
    current = build_collection_lock(
        project_root,
        experiment_id=locked.experiment_id,
        model=locked.model,
        ollama_model_digest=locked.ollama_model_digest,
        temperature=locked.temperature,
        top_p=locked.top_p,
        runtime_id=locked.runtime_id,
        schema_version=locked.schema_version,
        thinking_mode=locked.thinking_mode,
        max_output_tokens=locked.max_output_tokens,
        timeout_seconds=locked.timeout_seconds,
        retry_limit=locked.retry_limit,
        campaigns=locked.campaigns,
        seeds=locked.seeds,
        shuffle_seed=locked.shuffle_seed,
    )
    if current != locked:
        raise ValueError(f"analysis source differs from frozen collection: {lock_path}")
    return locked
