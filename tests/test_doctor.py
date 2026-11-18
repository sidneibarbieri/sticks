"""The preflight reads host state only and names an exact fix for each failure."""

import importlib.util
import ipaddress
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sticks_doctor", ROOT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = doctor
SPEC.loader.exec_module(doctor)


def test_compose_subnets_reads_list_and_mapping_forms(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "networks:\n"
        "  a:\n    ipam:\n      config:\n        - subnet: 172.20.0.0/24  # comment\n"
        "  b:\n    ipam:\n      config:\n        - gateway: 172.21.0.1\n          subnet: 172.21.0.0/24\n"
    )
    assert doctor.compose_subnets([compose]) == [
        ("docker-compose.yml", ipaddress.ip_network("172.20.0.0/24")),
        ("docker-compose.yml", ipaddress.ip_network("172.21.0.0/24")),
    ]


def test_compose_without_fixed_subnets_needs_no_network_check(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  db:\n    image: postgres\n")
    assert doctor.compose_subnets([compose]) == []


def test_review_path_checks_only_the_interpreter():
    checks = doctor.collect("review", Path.home(), [])
    assert [check.name for check in checks] == ["python", "python packages"]


def test_unvalidated_host_warns_without_blocking(monkeypatch):
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
    [check] = doctor.check_host()
    assert check.status == "WARN"
    assert "ARM64" in check.fix


def test_apple_silicon_is_the_validated_host(monkeypatch):
    monkeypatch.setattr(doctor.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(doctor.platform, "machine", lambda: "arm64")
    assert doctor.check_host()[0].status == "OK"


def test_duplicate_socket_daemon_names_the_stale_process(monkeypatch, tmp_path):
    socket_file = tmp_path / "socket_vmnet"
    socket_file.write_text("")

    class Lab:
        SOCKET_VMNET_BINARY = "/opt/socket_vmnet"
        DEFAULT_SOCKET_VMNET = socket_file

        @staticmethod
        def require_qemu_network(provider):
            raise RuntimeError("Expected exactly one socket_vmnet daemon; found 2")

    mtime = socket_file.stat().st_mtime
    monkeypatch.setattr(doctor, "socket_vmnet_daemons", lambda binary: [
        ("111", mtime - 86400, "older"), ("222", mtime - 1, "owner")])
    [check] = doctor.check_qemu_network(Lab)
    assert check.status == "FAIL"
    assert check.fix.startswith("sudo kill 111 ")
    assert "pid 222 owns the socket file" in check.fix
