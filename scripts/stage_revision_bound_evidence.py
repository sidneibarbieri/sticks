#!/usr/bin/env python3
"""Stage and revalidate private revision-bound execution evidence.

The command is intentionally private-only: it copies no source checkout,
does not sanitize data, and does not authorize publication.  Its purpose is
to make completed runtime receipts survive outside temporary directories while
preserving the exact evidence boundary that the runtime qualified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.controlled_comparison import (  # noqa: E402
    ConsumerExecutionReceipt,
    ExecutionHandoff,
    ExecutionSemanticBridge,
    IndependentEffectObservation,
)
from evaluation.execution_study import qualify_runtime_execution  # noqa: E402
from runners.capability_authority import verify_registered_observation  # noqa: E402
from runners.runtime_campaign_report import parse_retained_campaign_report  # noqa: E402


ROOT_FILES = (
    "admitted-plan.json",
    "execution-semantic-bridge.json",
    "execution-handoff.json",
    "consumer-receipt.json",
    "independent-observation.json",
)


class StagedCell(BaseModel):
    """One independently requalified execution cell in a private bundle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    campaign_id: str
    seed: int = Field(gt=0)
    consumer_revision: str
    effects: dict[str, int]


class EvidenceBundle(BaseModel):
    """Self-hashed index over private evidence files."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "revision-bound-evidence/v1"
    collection_lock_sha256: str
    cells: tuple[StagedCell, ...]
    files: dict[str, str]


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def safe_relative_path(value: str) -> Path:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("Evidence path is not a canonical relative POSIX path")
    return Path(*path.parts)


def _runtime_summary_path(run_root: Path) -> Path:
    summaries = tuple((run_root / "runtime" / "runtime-v2").glob("*/summary.json"))
    if len(summaries) != 1:
        raise ValueError("Expected exactly one retained runtime summary")
    return summaries[0]


def verify_execution_cell(run_root: Path, *, label: str) -> StagedCell:
    """Rebuild the receipt and observation from retained runtime bytes."""
    if run_root.is_symlink() or not run_root.is_dir():
        raise ValueError("Execution cell must be a real directory")
    for filename in ROOT_FILES:
        path = run_root / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Execution cell lacks a regular {filename}")
    handoff = ExecutionHandoff.model_validate_json(
        (run_root / "execution-handoff.json").read_text(encoding="utf-8")
    )
    receipt = ConsumerExecutionReceipt.model_validate_json(
        (run_root / "consumer-receipt.json").read_text(encoding="utf-8")
    )
    observation = IndependentEffectObservation.model_validate_json(
        (run_root / "independent-observation.json").read_text(encoding="utf-8")
    )
    if (
        not handoff.validate_hash()
        or not receipt.validate_hash()
        or not observation.validate_hash()
    ):
        raise ValueError("Execution cell contains an invalid content hash")
    if (
        receipt.handoff_sha256 != handoff.content_sha256
        or observation.handoff_sha256 != handoff.content_sha256
    ):
        raise ValueError("Execution receipt and observation identify another handoff")
    summary_path = _runtime_summary_path(run_root)
    raw_summary = summary_path.read_bytes()
    report = parse_retained_campaign_report(raw_summary.decode("utf-8"))
    for step in report.steps:
        if step.outcome is None:
            continue
        for reference, observed in zip(
            step.outcome.observation_references,
            step.outcome.observations,
            strict=True,
        ):
            retained = verify_registered_observation(
                reference,
                run_root=summary_path.parent,
                expected_scope=step.contract.scope,
                expected_predicate=observed.predicate_id,
            )
            if retained != observed:
                raise ValueError(
                    "Retained observation differs from the runtime summary"
                )
    rebuilt_receipt, rebuilt_observation = qualify_runtime_execution(
        handoff,
        ExecutionSemanticBridge.model_validate_json(
            (run_root / "execution-semantic-bridge.json").read_text(encoding="utf-8")
        ),
        report,
        raw_execution=raw_summary,
        admission_oracle_revision=observation.admission_oracle_revision,
    )
    if rebuilt_receipt != receipt or rebuilt_observation != observation:
        raise ValueError("Execution requalification differs from retained receipt")
    plan = json.loads((run_root / "admitted-plan.json").read_text(encoding="utf-8"))
    if plan.get("collection_lock_sha256") is None:
        raise ValueError("Admitted plan omits its collection lock")
    return StagedCell(
        label=label,
        campaign_id=handoff.campaign_id,
        seed=handoff.seed,
        consumer_revision=handoff.consumer_revision,
        effects=dict(
            Counter(effect.effect_class.value for effect in observation.effects)
        ),
    )


def _copy_tree(source: Path, destination: Path) -> None:
    resolved_source = source.resolve(strict=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_symlink():
            raise ValueError(f"Evidence bundle rejects symbolic links: {relative}")
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not path.is_file() or not path.resolve(strict=True).is_relative_to(
            resolved_source
        ):
            raise ValueError(f"Evidence bundle rejects special paths: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _file_manifest(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Evidence bundle contains a symbolic link")
        if path.is_file() and path.name != "manifest.json":
            relative = path.relative_to(root).as_posix()
            safe_relative_path(relative)
            files[relative] = sha256_file(path)
    return files


def verify_bundle(bundle_root: Path) -> EvidenceBundle:
    """Verify staged file hashes and each staged execution cell."""
    manifest_path = bundle_root / "manifest.json"
    manifest = EvidenceBundle.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if manifest.files != _file_manifest(bundle_root):
        raise ValueError("Evidence bundle file manifest differs from staged bytes")
    lock_path = bundle_root / "collection-lock.json"
    if sha256_file(lock_path) != manifest.collection_lock_sha256:
        raise ValueError("Evidence bundle collection lock differs from its manifest")
    for cell in manifest.cells:
        rebuilt = verify_execution_cell(
            bundle_root / "cells" / cell.label, label=cell.label
        )
        if rebuilt != cell:
            raise ValueError("Staged execution cell differs from bundle manifest")
    return manifest


def _validate_cells_for_staging(
    *,
    collection_dir: Path,
    run_roots: tuple[Path, ...],
    destination: Path,
    lock_sha256: str,
) -> tuple[tuple[Path, StagedCell], ...]:
    """Validate all source cells before creating any destination bytes."""
    if destination.is_relative_to(collection_dir):
        raise ValueError("Destination must be outside the source collection")
    validated_cells: list[tuple[Path, StagedCell]] = []
    labels: set[str] = set()
    resolved_roots: set[Path] = set()
    for raw_run_root in run_roots:
        run_root = raw_run_root.resolve(strict=True)
        if run_root in resolved_roots:
            raise ValueError("Evidence bundle repeats an execution cell")
        if destination.is_relative_to(run_root):
            raise ValueError("Destination must be outside every execution cell")
        resolved_roots.add(run_root)
        label = run_root.name
        safe_relative_path(label)
        if label in labels:
            raise ValueError("Evidence bundle repeats a cell label")
        labels.add(label)
        cell = verify_execution_cell(run_root, label=label)
        plan = json.loads((run_root / "admitted-plan.json").read_text(encoding="utf-8"))
        if plan["collection_lock_sha256"] != lock_sha256:
            raise ValueError("Execution cell is bound to another collection lock")
        validated_cells.append((run_root, cell))
    return tuple(validated_cells)


def stage_bundle(
    *, collection_dir: Path, run_roots: tuple[Path, ...], destination: Path
) -> EvidenceBundle:
    """Copy complete verified cells into a new private-only destination."""
    collection_dir = collection_dir.resolve(strict=True)
    lock_path = collection_dir / "collection-lock.json"
    if lock_path.is_symlink() or not lock_path.is_file():
        raise ValueError("Collection lacks a frozen lock")
    destination = destination.resolve()
    if destination.exists() or destination.is_relative_to(PROJECT_ROOT):
        raise ValueError("Destination must be new and outside the public artifact root")
    if not run_roots:
        raise ValueError("At least one execution cell is required")
    lock_sha256 = sha256_file(lock_path)
    validated_cells = _validate_cells_for_staging(
        collection_dir=collection_dir,
        run_roots=run_roots,
        destination=destination,
        lock_sha256=lock_sha256,
    )
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(lock_path, destination / "collection-lock.json")
    for run_root, cell in validated_cells:
        _copy_tree(run_root, destination / "cells" / cell.label)
    cells = tuple(cell for _, cell in validated_cells)
    manifest = EvidenceBundle(
        collection_lock_sha256=lock_sha256,
        cells=cells,
        files=_file_manifest(destination),
    )
    (destination / "manifest.json").write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return verify_bundle(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-dir", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path, action="append")
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    manifest = stage_bundle(
        collection_dir=args.collection_dir,
        run_roots=tuple(args.run_root),
        destination=args.destination,
    )
    print(manifest.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
