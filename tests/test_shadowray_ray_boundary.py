"""The Ray-like fixture must not manufacture initial-access evidence."""

import subprocess

from executors import executor_registry
from executors import shadowray_fixed_executors as shadowray
from executors.registry_initializer import initialize_registry


def test_absent_ray_service_fails_without_guest_mock(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)

    def guest_transport(**kwargs):
        assert kwargs["sut_profile_id"] == "0.shadowray"
        assert "mock_ray_api" not in kwargs["bash_script"]
        return subprocess.CompletedProcess([], 22, "", "HTTP 404")

    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", guest_transport)

    success, output, error, artifacts = shadowray.execute_t1190_shadowray_fixed(
        "0.shadowray", "0.shadowray"
    )

    assert not success
    assert output == ""
    assert error == "HTTP 404"
    assert len(artifacts) == 1


def test_ray_like_fixture_is_reported_as_http_observation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    marker = "[T1190] Ray-like service boundary observed"

    def guest_transport(**kwargs):
        assert "mock_ray_api" not in kwargs["bash_script"]
        assert kwargs.get("execution_user") == "rayuser"
        assert "/api/jobs/" in kwargs["bash_script"]
        return subprocess.CompletedProcess([], 0, marker, "")

    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", guest_transport)

    success, output, error, artifacts = shadowray.execute_t1190_shadowray_fixed(
        "0.shadowray", "0.shadowray"
    )

    assert success
    assert "HTTP fixture" in output
    assert not error
    assert len(artifacts) == 1


def test_registry_does_not_grant_initial_access_from_http_get(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    initialize_registry(force=True)
    monkeypatch.setattr(
        shadowray,
        "run_bash_on_target_vm",
        lambda **kwargs: subprocess.CompletedProcess(
            [], 0, "[T1190] Ray-like service boundary observed", ""
        ),
    )

    evidence = executor_registry.execute_technique(
        technique_id="T1190",
        available_capabilities=["network:http_available"],
        campaign_id="0.shadowray",
        sut_profile_id="0.shadowray",
    )

    assert evidence.status == "success"
    assert evidence.capabilities_produced == ["observation:ray_api_http"]
    assert "access:initial" not in evidence.capabilities_produced


def test_ray_http_observation_requires_guest_marker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    monkeypatch.setattr(
        shadowray,
        "run_bash_on_target_vm",
        lambda **kwargs: subprocess.CompletedProcess([], 0, "other service", ""),
    )

    success, _, error, _ = shadowray.execute_t1190_shadowray_fixed(
        "0.shadowray", "0.shadowray"
    )

    assert not success
    assert "observation missing" in error
