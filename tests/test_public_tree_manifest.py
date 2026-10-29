from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / "scripts" / "public_tree_manifest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "sticks_public_tree_manifest", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_rejects_modification_and_unexpected_file(tmp_path: Path) -> None:
    module = _load_module()
    source = tmp_path / "source.txt"
    source.write_text("stable\n", encoding="utf-8")
    manifest = tmp_path / module.DEFAULT_MANIFEST_NAME
    module.write_manifest(tmp_path, manifest)
    module.verify_manifest(tmp_path, manifest)

    source.write_text("changed\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="modified"):
        module.verify_manifest(tmp_path, manifest)

    source.write_text("stable\n", encoding="utf-8")
    (tmp_path / "unexpected.txt").write_text("new\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unexpected"):
        module.verify_manifest(tmp_path, manifest)


def test_declared_runtime_outputs_do_not_change_tree_hash(tmp_path: Path) -> None:
    module = _load_module()
    (tmp_path / "source.txt").write_text("stable\n", encoding="utf-8")
    manifest = tmp_path / module.DEFAULT_MANIFEST_NAME
    payload = module.write_manifest(tmp_path, manifest)
    results = tmp_path / "results"
    results.mkdir()
    (results / "public_surface_report.json").write_text("{}\n", encoding="utf-8")
    (results / "PUBLIC_SURFACE_REPORT.md").write_text("clean\n", encoding="utf-8")

    observed = module.verify_manifest(tmp_path, manifest)

    assert observed["tree_sha256"] == payload["tree_sha256"]


def test_install_metadata_does_not_invalidate_manifest(tmp_path: Path) -> None:
    module = _load_module()
    (tmp_path / "source.txt").write_text("stable\n", encoding="utf-8")
    manifest = tmp_path / module.DEFAULT_MANIFEST_NAME
    module.write_manifest(tmp_path, manifest)
    metadata = tmp_path / "src/sticks.egg-info"
    metadata.mkdir(parents=True)
    (metadata / "PKG-INFO").write_text("generated\n", encoding="utf-8")

    module.verify_manifest(tmp_path, manifest)

    (tmp_path / "src/extra.py").write_text("unexpected\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unexpected"):
        module.verify_manifest(tmp_path, manifest)


def test_prospective_runs_are_excluded_but_other_new_files_are_rejected(
    tmp_path: Path,
) -> None:
    module = _load_module()
    (tmp_path / "source.txt").write_text("stable\n", encoding="utf-8")
    manifest = tmp_path / module.DEFAULT_MANIFEST_NAME
    module.write_manifest(tmp_path, manifest)

    run_dir = tmp_path / "runs" / "lab-batches" / "batch-1"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.tsv").write_text("campaign\tstatus\n", encoding="utf-8")
    artifacts_dir = tmp_path / "data" / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "command.log").write_text("observed\n", encoding="utf-8")
    vagrant_dir = tmp_path / "lab" / "vagrant" / "target-linux-1" / ".vagrant"
    vagrant_dir.mkdir(parents=True)
    (vagrant_dir / "global.sol").write_text("runtime\n", encoding="utf-8")
    module.verify_manifest(tmp_path, manifest)

    (tmp_path / "unexpected.txt").write_text("new\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unexpected"):
        module.verify_manifest(tmp_path, manifest)


@pytest.mark.parametrize("command", ["write", "verify"])
@pytest.mark.parametrize("manifest_mode", ["default", "relative", "absolute"])
def test_cli_resolves_manifest_in_declared_root(
    tmp_path: Path, command: str, manifest_mode: str
) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    (package_root / "source.txt").write_text("stable\n", encoding="utf-8")
    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / "PUBLIC_TREE_SHA256.json").write_text("not a manifest", encoding="utf-8")
    manifest = package_root / "PUBLIC_TREE_SHA256.json"
    if command == "verify":
        _load_module().write_manifest(package_root, manifest)
    arguments = [sys.executable, str(MODULE_PATH), command, "--root", str(package_root)]
    if manifest_mode != "default":
        arguments.extend(
            [
                "--manifest",
                manifest.name if manifest_mode == "relative" else str(manifest),
            ]
        )

    result = subprocess.run(
        arguments, cwd=caller, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["file_count"] == 1
    assert set(payload["files"]) == {"source.txt"}
    assert (caller / manifest.name).read_text(encoding="utf-8") == "not a manifest"


@pytest.mark.parametrize("manifest_mode", ["default", "relative", "absolute"])
def test_cli_rejects_modified_package_from_other_directory(
    tmp_path: Path, manifest_mode: str
) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    source = package_root / "source.txt"
    source.write_text("stable\n", encoding="utf-8")
    manifest = package_root / "PUBLIC_TREE_SHA256.json"
    _load_module().write_manifest(package_root, manifest)
    source.write_text("modified\n", encoding="utf-8")
    arguments = [
        sys.executable, str(MODULE_PATH), "verify", "--root", str(package_root)
    ]
    if manifest_mode != "default":
        arguments.extend(
            [
                "--manifest",
                manifest.name if manifest_mode == "relative" else str(manifest),
            ]
        )

    result = subprocess.run(
        arguments, cwd=tmp_path, capture_output=True, text=True, check=False
    )

    assert result.returncode != 0
    assert "public tree integrity failure" in result.stderr
    assert "source.txt" in result.stderr
