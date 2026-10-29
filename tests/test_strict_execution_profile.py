from pathlib import Path
import hashlib
import json

import pytest

from runners import strict_execution_profile as profile_module
from scripts import freeze_prepared_c0045_runtime as freezer


def test_strict_profile_binds_the_attested_offline_runtime() -> None:
    profile = profile_module.load_strict_execution_profile()
    runtime = profile_module.load_prepared_runtime_manifest(profile)

    assert profile_module.strict_profile_version(profile.schema_version) >= 8
    assert profile.mode == "strict_experiment"
    assert set(profile.vagrantfile_sha256) == {"caldera", "attacker", "target-linux-1"}
    assert set(runtime.images) == set(profile.vagrantfile_sha256)


def test_prepared_runtime_manifest_requires_provisioning_inventory() -> None:
    with pytest.raises(ValueError, match="bind every provisioning input"):
        profile_module.PreparedRuntimeManifest(
            schema_version="c0045-prepared-runtime-manifest/v5",
            images={
                "caldera": profile_module.PreparedRuntimeImage(
                    box_name="sticks/c0045-caldera-arm64",
                    box_version="1",
                    image_fingerprint_sha256="a" * 64,
                    guest_inventory_sha256="b" * 64,
                ),
                "attacker": profile_module.PreparedRuntimeImage(
                    box_name="sticks/c0045-attacker-arm64",
                    box_version="1",
                    image_fingerprint_sha256="c" * 64,
                    guest_inventory_sha256="d" * 64,
                ),
                "target-linux-1": profile_module.PreparedRuntimeImage(
                    box_name="sticks/c0045-target-arm64",
                    box_version="1",
                    image_fingerprint_sha256="e" * 64,
                    guest_inventory_sha256="f" * 64,
                ),
            },
            provisioning_input_sha256={},
        )


def test_prepared_runtime_v8_rejects_wrong_qemu_plugin_box_format() -> None:
    image = profile_module.PreparedRuntimeImage(
        box_name="sticks/c0045-role-arm64",
        box_version="0",
        image_fingerprint_sha256="a" * 64,
        guest_inventory_sha256="b" * 64,
    )
    with pytest.raises(ValueError, match="libvirt box format"):
        profile_module.PreparedRuntimeManifest(
            schema_version="c0045-prepared-runtime-manifest/v8",
            images={role: image for role in ("caldera", "attacker", "target-linux-1")},
            provisioning_input_sha256={"lab/vagrant/shared/caldera.sh": "c" * 64},
        )


def test_profile_loads_its_declared_prepared_runtime_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experiments = tmp_path / "data" / "experiments"
    experiments.mkdir(parents=True)
    monkeypatch.setattr(profile_module, "ARTIFACT_ROOT", tmp_path)

    def manifest_payload(revision: int) -> bytes:
        return (
            json.dumps(
                {
                    "schema_version": f"c0045-prepared-runtime-manifest/v{revision}",
                    "images": {
                        "caldera": {
                            "box_name": "caldera",
                            "box_version": "0",
                            "image_fingerprint_sha256": "a" * 64,
                            "guest_inventory_sha256": "b" * 64,
                        },
                        "attacker": {
                            "box_name": "attacker",
                            "box_version": "0",
                            "image_fingerprint_sha256": "c" * 64,
                            "guest_inventory_sha256": "d" * 64,
                        },
                        "target-linux-1": {
                            "box_name": "target",
                            "box_version": "0",
                            "image_fingerprint_sha256": "e" * 64,
                            "guest_inventory_sha256": "f" * 64,
                        },
                    },
                    "provisioning_input_sha256": {
                        "lab/vagrant/shared/base.sh": "1" * 64
                    },
                },
                indent=2,
            )
            + "\n"
        ).encode("utf-8")

    v5_path = experiments / "c0045_prepared_runtime_manifest_v5.json"
    v6_path = experiments / "c0045_prepared_runtime_manifest_v6.json"
    v5_path.write_bytes(manifest_payload(5))
    v6_path.write_bytes(manifest_payload(6))
    profile = profile_module.StrictExecutionProfile(
        schema_version="c0045-strict-execution-profile/v12",
        mode="strict_experiment",
        provider="qemu",
        minimum_vagrant_qemu_version="0.6.3",
        requirements_lock_sha256="a" * 64,
        series_sha256="b" * 64,
        study_sha256="c" * 64,
        vagrantfile_sha256={"caldera": "d" * 64, "attacker": "e" * 64, "target-linux-1": "f" * 64},
        provisioning_input_sha256={"lab/vagrant/shared/base.sh": "1" * 64},
        prepared_runtime_manifest_path="data/experiments/c0045_prepared_runtime_manifest_v6.json",
        prepared_runtime_manifest_sha256=hashlib.sha256(v6_path.read_bytes()).hexdigest(),
        execution_source_sha256="2" * 64,
        execution_source_paths=("scripts/run_strict_c0045_effect_series.py",),
    )

    assert (
        profile_module.load_prepared_runtime_manifest(profile).schema_version
        == "c0045-prepared-runtime-manifest/v6"
    )


def test_prepared_runtime_environment_maps_each_role_to_its_own_box() -> None:
    manifest = profile_module.PreparedRuntimeManifest(
        schema_version="c0045-prepared-runtime-manifest/v5",
        images={
            "caldera": profile_module.PreparedRuntimeImage(
                box_name="sticks/c0045-caldera-arm64",
                box_version="1",
                image_fingerprint_sha256="a" * 64,
                guest_inventory_sha256="b" * 64,
            ),
            "attacker": profile_module.PreparedRuntimeImage(
                box_name="sticks/c0045-attacker-arm64",
                box_version="1",
                image_fingerprint_sha256="c" * 64,
                guest_inventory_sha256="d" * 64,
            ),
            "target-linux-1": profile_module.PreparedRuntimeImage(
                box_name="sticks/c0045-target-arm64",
                box_version="1",
                image_fingerprint_sha256="e" * 64,
                guest_inventory_sha256="f" * 64,
            ),
        },
        provisioning_input_sha256={"lab/vagrant/shared/base.sh": "f" * 64},
    )

    environment = profile_module.strict_prepared_environment(manifest)

    assert environment["STICKS_STRICT_PREPARED"] == "1"
    assert environment["STICKS_STRICT_BOX_CALDERA"] == "sticks/c0045-caldera-arm64"
    assert environment["STICKS_STRICT_BOX_ATTACKER"] == "sticks/c0045-attacker-arm64"
    assert environment["STICKS_STRICT_BOX_TARGET"] == "sticks/c0045-target-arm64"


def test_image_tree_fingerprint_changes_when_content_changes(tmp_path: Path) -> None:
    image_root = tmp_path / "image"
    image_root.mkdir()
    artifact = image_root / "disk.qcow2"
    artifact.write_bytes(b"first")
    first = profile_module.image_tree_sha256(image_root)
    artifact.write_bytes(b"second")

    assert profile_module.image_tree_sha256(image_root) != first


def test_next_strict_profile_path_follows_the_latest_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experiments = tmp_path / "data" / "experiments"
    experiments.mkdir(parents=True)
    (experiments / "c0045_strict_execution_profile_v11.json").write_text(
        "{}\n", encoding="utf-8"
    )
    monkeypatch.setattr(profile_module, "ARTIFACT_ROOT", tmp_path)

    revision, path = profile_module.next_strict_profile_path()

    assert revision == 12
    assert path == experiments / "c0045_strict_execution_profile_v12.json"


def test_image_tree_fingerprint_rejects_empty_image_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="contains no regular files"):
        profile_module.image_tree_sha256(tmp_path)


def test_execution_source_fingerprint_binds_source_not_bytecode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "lab").mkdir()
    source = tmp_path / "src/runner.py"
    source.write_text("value = 1\n", encoding="utf-8")
    bytecode = tmp_path / "src/runner.pyc"
    bytecode.write_bytes(b"first")
    (tmp_path / "scripts/run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "lab/health_check.py").write_text("pass\n", encoding="utf-8")
    monkeypatch.setattr(profile_module, "ARTIFACT_ROOT", tmp_path)

    first = profile_module.strict_execution_source_sha256(
        "c0045-strict-execution-profile/v7"
    )
    bytecode.write_bytes(b"second")
    assert (
        profile_module.strict_execution_source_sha256(
            "c0045-strict-execution-profile/v7"
        )
        == first
    )
    source.write_text("value = 2\n", encoding="utf-8")
    assert (
        profile_module.strict_execution_source_sha256(
            "c0045-strict-execution-profile/v7"
        )
        != first
    )


def test_v8_execution_source_fingerprint_tracks_only_transitive_runtime_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src" / "runners").mkdir(parents=True)
    (tmp_path / "lab").mkdir()
    entrypoint = tmp_path / "scripts" / "run.py"
    entrypoint.write_text(
        "from runners.runtime import execute\nexecute()\n", encoding="utf-8"
    )
    runtime = tmp_path / "src" / "runners" / "runtime.py"
    runtime.write_text(
        "from runners.effect import observe\ndef execute():\n    observe()\n",
        encoding="utf-8",
    )
    effect = tmp_path / "src" / "runners" / "effect.py"
    effect.write_text("def observe():\n    return 'observed'\n", encoding="utf-8")
    packaging = tmp_path / "scripts" / "package.py"
    packaging.write_text("def package():\n    return 'distribution'\n", encoding="utf-8")
    monkeypatch.setattr(profile_module, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(profile_module, "STRICT_EXECUTION_ENTRYPOINTS", (Path("scripts/run.py"),))

    first = profile_module.strict_execution_source_sha256(
        "c0045-strict-execution-profile/v8"
    )
    packaging.write_text("def package():\n    return 'changed distribution'\n", encoding="utf-8")
    assert (
        profile_module.strict_execution_source_sha256(
            "c0045-strict-execution-profile/v8"
        )
        == first
    )
    effect.write_text("def observe():\n    return 'changed effect'\n", encoding="utf-8")
    assert (
        profile_module.strict_execution_source_sha256(
            "c0045-strict-execution-profile/v8"
        )
        != first
    )


def test_v8_profile_requires_a_reviewable_execution_source_inventory() -> None:
    with pytest.raises(ValueError, match="must list execution sources"):
        profile_module.StrictExecutionProfile(
            schema_version="c0045-strict-execution-profile/v10",
            mode="strict_experiment",
            provider="qemu",
            minimum_vagrant_qemu_version="0.6.3",
            requirements_lock_sha256="a" * 64,
            series_sha256="b" * 64,
            study_sha256="c" * 64,
            vagrantfile_sha256={
                "caldera": "d" * 64,
                "attacker": "e" * 64,
                "target-linux-1": "f" * 64,
            },
            provisioning_input_sha256={"lab/vagrant/shared/base.sh": "1" * 64},
            prepared_runtime_manifest_sha256="2" * 64,
            execution_source_sha256="3" * 64,
        )


def test_freezer_binds_the_manifest_path_into_the_runtime_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = profile_module.PreparedRuntimeManifest(
        schema_version="c0045-prepared-runtime-manifest/v5",
        images={
            "caldera": profile_module.PreparedRuntimeImage(
                box_name="sticks/c0045-caldera-arm64",
                box_version="0",
                image_fingerprint_sha256="a" * 64,
                guest_inventory_sha256="b" * 64,
            ),
            "attacker": profile_module.PreparedRuntimeImage(
                box_name="sticks/c0045-attacker-arm64",
                box_version="0",
                image_fingerprint_sha256="c" * 64,
                guest_inventory_sha256="d" * 64,
            ),
            "target-linux-1": profile_module.PreparedRuntimeImage(
                box_name="sticks/c0045-target-linux-1-arm64",
                box_version="0",
                image_fingerprint_sha256="e" * 64,
                guest_inventory_sha256="f" * 64,
            ),
        },
        provisioning_input_sha256={"lab/vagrant/shared/base.sh": "1" * 64},
    )
    monkeypatch.setattr(freezer, "sha256_file", lambda _path: "2" * 64)
    monkeypatch.setattr(
        freezer,
        "strict_execution_source_sha256",
        lambda schema_version: "3" * 64,
    )
    monkeypatch.setattr(
        freezer,
        "strict_execution_dependency_relative_paths",
        lambda: ("scripts/run_strict_c0045_effect_series.py",),
    )

    profile = freezer._strict_profile(
        manifest,
        profile_module.ARTIFACT_ROOT
        / "data/experiments/c0045_prepared_runtime_manifest_v5.json",
        10,
    )

    assert profile.schema_version == "c0045-strict-execution-profile/v10"
    assert profile.execution_source_paths == (
        "scripts/run_strict_c0045_effect_series.py",
    )
    assert (
        profile.prepared_runtime_manifest_path
        == "data/experiments/c0045_prepared_runtime_manifest_v5.json"
    )
