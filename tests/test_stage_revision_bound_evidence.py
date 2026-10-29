from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "stage_revision_bound_evidence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "stage_revision_bound_evidence", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value", ("", "/absolute", "a/../b", "a\\b"))
def test_safe_relative_path_rejects_unsafe_values(value: str) -> None:
    module = _load_module()

    with pytest.raises(ValueError, match="canonical relative POSIX path"):
        module.safe_relative_path(value)


def test_stage_bundle_rejects_destination_inside_collection_before_copying(
    tmp_path: Path,
) -> None:
    module = _load_module()
    collection = tmp_path / "collection"
    collection.mkdir()
    (collection / "collection-lock.json").write_text("{}", encoding="utf-8")
    run_root = tmp_path / "C0010-seed1"
    run_root.mkdir()
    destination = collection / "private-bundle"

    with pytest.raises(ValueError, match="outside the source collection"):
        module.stage_bundle(
            collection_dir=collection,
            run_roots=(run_root,),
            destination=destination,
        )

    assert not destination.exists()


def test_stage_bundle_rejects_destination_inside_source_cell_before_copying(
    tmp_path: Path,
) -> None:
    module = _load_module()
    collection = tmp_path / "collection"
    collection.mkdir()
    (collection / "collection-lock.json").write_text("{}", encoding="utf-8")
    run_root = tmp_path / "C0010-seed1"
    run_root.mkdir()
    destination = run_root / "private-bundle"

    with pytest.raises(ValueError, match="outside every execution cell"):
        module.stage_bundle(
            collection_dir=collection,
            run_roots=(run_root,),
            destination=destination,
        )

    assert not destination.exists()
