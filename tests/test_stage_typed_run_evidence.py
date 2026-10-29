"""Private evidence staging copies only manifest-bound run files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import stage_typed_run_evidence as staging


def write_file(path: Path, content: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = content.encode("utf-8")
    path.write_bytes(encoded)
    return {
        "path": path.name,
        "size": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def synthetic_run(root: Path) -> dict:
    root.mkdir()
    receipt = {"campaign_id": "0.c0010", "cycle_passed": True}
    source = write_file(root / "workspace/src/main.py", "print('safe')\n")
    source["path"] = "src/main.py"
    artifact = write_file(root / "workspace/data/artifacts/proof.txt", "proof\n")
    write_json(root / "source_manifest.json", {"files": [source]})
    write_json(root / "artifact_manifest.json", {"files": [artifact]})
    write_json(root / "evidence_manifest.json", {"files": []})
    write_json(root / "run_context.json", {"campaign_id": "0.c0010"})
    write_json(root / "final_run_receipt.json", receipt)
    write_file(root / "execution.log", "completed\n")
    write_file(root / "evidence/summary.json", "{}")
    write_file(root / "workspace/src/__pycache__/main.pyc", "cache")
    write_file(root / "workspace/lab/vagrant/target/.vagrant/id", "local VM ID")
    return receipt


def test_stages_only_declared_source_and_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    receipt = synthetic_run(source)
    monkeypatch.setattr(staging, "build_receipt", lambda unused_root: receipt)

    destination = tmp_path / "bundle"
    rows = staging.stage_runs([source], destination)

    assert rows[0].campaign_id == "0.c0010"
    assert (destination / "c0010/workspace/src/main.py").is_file()
    assert (destination / "c0010/workspace/data/artifacts/proof.txt").is_file()
    reference = json.loads(
        (destination / "c0010/workspace/PUBLIC_TREE_SHA256.json").read_text(
            encoding="utf-8"
        )
    )
    assert reference == staging.source_reference_manifest(
        json.loads((source / "source_manifest.json").read_text(encoding="utf-8"))
    )
    assert (destination / "c0010/evidence/summary.json").is_file()
    assert not (destination / "c0010/workspace/src/__pycache__").exists()
    assert not (destination / "c0010/workspace/lab/vagrant/target/.vagrant").exists()


def test_preserves_source_manifest_already_bound_to_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    receipt = synthetic_run(source)
    reference_content = '{"tree_sha256":"original-source"}\n'
    entry = write_file(
        source / "workspace/PUBLIC_TREE_SHA256.json", reference_content
    )
    manifest_path = source / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"].append(entry)
    write_json(manifest_path, manifest)
    monkeypatch.setattr(staging, "build_receipt", lambda unused_root: receipt)

    destination = tmp_path / "bundle"
    staging.stage_run(source, destination)

    assert (
        destination / "workspace/PUBLIC_TREE_SHA256.json"
    ).read_text(encoding="utf-8") == reference_content


def test_removes_vagrant_state_created_by_receipt_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    receipt = synthetic_run(source)

    def receipt_check(run_root: Path) -> dict:
        if run_root != source:
            write_file(
                run_root / "workspace/lab/vagrant/target/.vagrant/rgloader/loader.rb",
                "generated\n",
            )
        return receipt

    monkeypatch.setattr(staging, "build_receipt", receipt_check)
    destination = tmp_path / "bundle"
    staging.stage_run(source, destination)

    assert not (destination / "workspace/lab/vagrant/target/.vagrant").exists()


def test_rejects_other_unbound_workspace_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    receipt = synthetic_run(source)

    def receipt_check(run_root: Path) -> dict:
        if run_root != source:
            write_file(run_root / "workspace/unbound.txt", "unexpected\n")
        return receipt

    monkeypatch.setattr(staging, "build_receipt", receipt_check)
    with pytest.raises(ValueError, match="unbound or missing"):
        staging.stage_run(source, tmp_path / "bundle")


def test_rejects_symlink_created_during_receipt_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    receipt = synthetic_run(source)

    def receipt_check(run_root: Path) -> dict:
        if run_root != source:
            (run_root / "workspace/linked").symlink_to("src/main.py")
        return receipt

    monkeypatch.setattr(staging, "build_receipt", receipt_check)
    with pytest.raises(ValueError, match="symbolic link"):
        staging.stage_run(source, tmp_path / "bundle")


def test_rejects_manifest_traversal(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="unsafe path"):
        staging.copy_manifest_tree(
            source, tmp_path / "target", {"files": [{"path": "../escape"}]}
        )


def test_rejects_symlinked_manifest_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    (source / "linked.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="outside its root"):
        staging.copy_manifest_tree(
            source, tmp_path / "target", {"files": [{"path": "linked.txt"}]}
        )


def test_rejects_repository_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="outside the repository"):
        staging.stage_runs([source], staging.ARTIFACT_ROOT / "private-run-bundle")


def test_rejects_unverified_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    synthetic_run(source)
    monkeypatch.setattr(staging, "build_receipt", lambda unused_root: {})
    with pytest.raises(ValueError, match="does not verify"):
        staging.stage_run(source, tmp_path / "bundle")
