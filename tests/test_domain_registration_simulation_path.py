"""Simulation output must not depend on the launch directory."""

import json

from executors import executor_registry


def test_domain_registration_simulation_uses_configured_artifact_root(monkeypatch, tmp_path):
    artifact_root = tmp_path / "simulation" / "artifacts"
    launch_dir = tmp_path / "unrelated"
    launch_dir.mkdir()
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", artifact_root)
    monkeypatch.chdir(launch_dir)

    completed, _, error, artifact_paths = executor_registry.execute_t1583_001_simulated(
        "0.c0026", "0.c0026"
    )

    expected_file = artifact_root / "domain_registration.json"
    assert completed is True
    assert error == ""
    assert artifact_paths == [str(expected_file)]
    assert json.loads(expected_file.read_text(encoding="utf-8"))["evidence_kind"] == "simulation_record"
    assert not (launch_dir / "data").exists()
