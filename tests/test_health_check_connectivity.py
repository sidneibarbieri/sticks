from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


HEALTH_CHECK = Path(__file__).resolve().parent.parent / "lab" / "health_check.py"


def load_health_check():
    specification = importlib.util.spec_from_file_location(
        "sticks_health_check_connectivity", HEALTH_CHECK
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


@pytest.mark.parametrize("provider", ["qemu", "libvirt"])
@pytest.mark.parametrize(
    ("return_code", "stdout", "expected_pass"),
    [
        (0, "REACHABLE\n", True),
        (0, "ping output\nREACHABLE\n", True),
        (0, "UNREACHABLE\n", False),
        (0, "REACHABLE\nUNREACHABLE\n", False),
        (1, "REACHABLE\n", False),
        (0, "unrelated output\n", False),
    ],
)
def test_host_to_host_requires_exact_success_marker(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    return_code: int,
    stdout: str,
    expected_pass: bool,
) -> None:
    health_check = load_health_check()
    command_result = subprocess.CompletedProcess(
        args=["connectivity-probe"], returncode=return_code, stdout=stdout, stderr=""
    )
    monkeypatch.setattr(health_check, "_run_vagrant_ssh", lambda *args, **kwargs: command_result)
    monkeypatch.setattr(health_check, "_run_cmd", lambda *args, **kwargs: command_result)

    result = health_check.check_host_to_host("attacker", "target-linux-1", provider)

    assert result.passed is expected_pass


def test_topology_without_campaign_readiness_check_fails() -> None:
    health_check = load_health_check()

    checks = health_check.level3_campaign_ready(
        ["target-linux-1"], "0.c0026", "qemu"
    )

    assert len(checks) == 1
    assert checks[0].name == "campaign-readiness"
    assert checks[0].passed is False


@pytest.mark.parametrize("return_code", [0, 1])
def test_attacker_to_caldera_api_is_a_required_private_network_probe(
    monkeypatch: pytest.MonkeyPatch, return_code: int
) -> None:
    health_check = load_health_check()
    command_result = subprocess.CompletedProcess(
        args=["vagrant", "ssh"], returncode=return_code, stdout="", stderr="failed"
    )
    monkeypatch.setattr(
        health_check, "_run_vagrant_ssh", lambda *args, **kwargs: command_result
    )

    result = health_check.check_attacker_to_caldera_api("qemu")

    assert result.passed is (return_code == 0)
    assert result.name == "attacker->caldera-api"


def test_campaign_readiness_includes_attacker_to_caldera_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    health_check = load_health_check()
    monkeypatch.setattr(
        health_check,
        "check_attacker_to_caldera_api",
        lambda _provider: health_check.CheckResult("attacker->caldera-api", True, "ok"),
    )
    monkeypatch.setattr(
        health_check,
        "check_host_to_host",
        lambda source, target, _provider: health_check.CheckResult(
            f"{source}->{target}", True, "ok"
        ),
    )

    checks = health_check.level3_campaign_ready(
        ["caldera", "attacker", "target-linux-1"], "0.shadowray", "qemu"
    )

    assert checks[0].name == "attacker->caldera-api"
