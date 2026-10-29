from __future__ import annotations

import os
import socket
import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VM_NAMES = ("caldera", "attacker", "target-linux-1", "target-linux-2")


@pytest.mark.parametrize("daemon_count", [0, 1, 2])
def test_socket_preflight_requires_exactly_one_daemon(
    tmp_path: Path, daemon_count: int
) -> None:
    source = (PROJECT_ROOT / "scripts/up_lab.sh").read_text(encoding="utf-8")
    start = source.index("require_single_socket_vmnet_daemon() {")
    end = source.index("\n}\n", start) + 3
    binary = "/opt/homebrew/opt/socket_vmnet/bin/socket_vmnet"
    processes = "\n".join(
        f"{100 + index} {binary} --test" for index in range(daemon_count)
    )
    fake_ps = tmp_path / "ps"
    fake_ps.write_text(f"#!/bin/sh\nprintf '%s\\n' '{processes}'\n", encoding="utf-8")
    fake_ps.chmod(0o755)
    command = (
        'set -euo pipefail\nSOCKET_VMNET_SOCKET="test"\n'
        'log_error() { echo "$*" >&2; }\nlog_info() { echo "$*"; }\n'
        + source[start:end]
        + "\nrequire_single_socket_vmnet_daemon"
    )
    environment = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}")
    result = subprocess.run(
        ["bash", "-c", command], env=environment, capture_output=True, text=True
    )

    assert (result.returncode == 0) == (daemon_count == 1)
    if daemon_count == 1:
        assert "pid 100" in result.stdout
    else:
        assert f"found {daemon_count}" in result.stderr


def test_qemu_lab_uses_a_pinned_box_and_an_explicit_private_network_backend() -> None:
    """Keep ARM64 QEMU networking explicit for multi-host campaigns."""
    for vm_name in ("caldera", "attacker", "target-linux-1"):
        vagrantfile = PROJECT_ROOT / "lab" / "vagrant" / vm_name / "Vagrantfile"
        source = vagrantfile.read_text(encoding="utf-8")

        assert "config.vm.box = strict_prepared ? ENV.fetch(" in source
        assert '"perk/ubuntu-2204-arm64"' in source
        assert "config.vm.box_version = strict_prepared ? ENV.fetch(" in source
        assert '"20250702"' in source
        assert "qemu.advanced_network = true" in source
        assert "qemu.net_mode = :socket_vmnet" in source
        assert (
            'qemu.socket_vmnet_socket = ENV.fetch("STICKS_SOCKET_VMNET_SOCKET"'
            in source
        )


@pytest.mark.parametrize("listening", [False, True])
def test_socket_preflight_checks_a_live_listener(listening: bool) -> None:
    source = (PROJECT_ROOT / "scripts/up_lab.sh").read_text(encoding="utf-8")
    start = source.index("require_socket_vmnet() {")
    end = source.index("\n}\n", start) + 3
    command = (
        'set -euo pipefail\nSOCKET_VMNET_SOCKET="$1"\n'
        'log_error() { echo "$*" >&2; }\n'
        + source[start:end]
        + "\nrequire_socket_vmnet"
    )
    with (
        TemporaryDirectory(prefix="vmnet-", dir="/tmp") as socket_directory,
        socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener,
    ):
        socket_path = Path(socket_directory) / "vmnet.sock"
        listener.bind(str(socket_path))
        if listening:
            listener.listen(1)
        result = subprocess.run(
            ["bash", "-c", command, "socket-preflight", str(socket_path)],
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == (0 if listening else 1)


def test_qemu_preflight_accepts_the_documented_libvirt_box_import_path() -> None:
    source = (PROJECT_ROOT / "scripts" / "up_lab.sh").read_text(encoding="utf-8")

    assert "box_supports_qemu_import" in source
    assert "libvirt" in source
    assert "socket_vmnet" in source


def test_qemu_lab_uses_distinct_offset_ssh_ports() -> None:
    source = (PROJECT_ROOT / "scripts" / "up_lab.sh").read_text(encoding="utf-8")
    allocator = (
        PROJECT_ROOT / "lab" / "vagrant" / "shared" / "qemu_ssh_port.rb"
    ).read_text(encoding="utf-8")

    assert "kill_stale_listener" not in source
    assert 'OFFSET_ENVIRONMENT = "STICKS_QEMU_PORT_OFFSET"' in allocator
    assert "MAX_OFFSET = 1_000" in allocator
    assert 'Integer(ENV.fetch(OFFSET_ENVIRONMENT, "0"), 10)' in allocator
    for ssh_port, vm_name in enumerate(VM_NAMES, start=2201):
        vagrantfile = PROJECT_ROOT / "lab" / "vagrant" / vm_name / "Vagrantfile"
        contents = vagrantfile.read_text(encoding="utf-8")
        assert 'require_relative "../shared/qemu_ssh_port"' in contents
        assert f"ssh_port = SticksQemuSshPort.for({ssh_port})" in contents
        assert "qemu.ssh_port = ssh_port" in contents
        assert "qemu.ssh_auto_correct = false" in contents
        assert "host: ssh_port" in contents
        assert 'id: "ssh", auto_correct: false, disabled: true' in contents


def test_strict_qemu_lab_disables_host_shared_folders() -> None:
    for vm_name in ("caldera", "attacker", "target-linux-1"):
        source = (PROJECT_ROOT / "lab" / "vagrant" / vm_name / "Vagrantfile").read_text(
            encoding="utf-8"
        )
        assert (
            'config.vm.synced_folder ".", "/vagrant", disabled: true if strict_prepared'
            in source
        )


def test_caldera_uses_the_shared_private_network_without_duplicate_port_forwards() -> (
    None
):
    source = (PROJECT_ROOT / "lab" / "vagrant" / "caldera" / "Vagrantfile").read_text(
        encoding="utf-8"
    )

    assert 'config.vm.network "private_network", ip: "192.168.56.10"' in source
    assert source.count('config.vm.network "forwarded_port"') == 1
    assert 'id: "ssh", auto_correct: false, disabled: true' in source


def test_qemu_preflight_rejects_a_provider_without_advanced_network(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_vagrant = fake_bin / "vagrant"
    fake_vagrant.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = plugin ]; then echo 'vagrant-qemu (0.3.12, global)'; exit 0; fi\n"
        "echo 'unexpected vagrant invocation' >&2; exit 9\n",
        encoding="utf-8",
    )
    fake_vagrant.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

    result = subprocess.run(
        [
            "bash",
            str(PROJECT_ROOT / "scripts" / "up_lab.sh"),
            "--campaign",
            "0.c0010",
            "--provider",
            "qemu",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode != 0
    assert "vagrant-qemu 0.6.3." in result.stderr
    assert "unexpected vagrant invocation" not in result.stderr


def test_qemu_uses_host_acceleration_defaults() -> None:
    for vm_name in VM_NAMES:
        source = (PROJECT_ROOT / "lab" / "vagrant" / vm_name / "Vagrantfile").read_text(
            encoding="utf-8"
        )
        assert "qemu.machine =" not in source
        assert "qemu.cpu =" not in source


def test_caldera_readiness_cannot_be_inferred_from_an_unrelated_host_process() -> None:
    source = (PROJECT_ROOT / "scripts" / "up_lab.sh").read_text(encoding="utf-8")

    assert 'local private_url="http://192.168.56.10:8888/"' in source
    assert (
        'vagrant ssh -c "curl -fsS --connect-timeout 3 --max-time 5 $private_url -o /dev/null"'
        in source
    )
    assert "attempt=$((attempt + 1))" in source
    assert "((attempt++))" not in source
    assert "pgrep -f server.py" not in source
    assert "forwarded_url" not in source
