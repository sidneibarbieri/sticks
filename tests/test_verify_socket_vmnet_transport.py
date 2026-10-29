"""Tests for the runtime gate on socket_vmnet's QEMU transport."""

import pytest

from scripts.verify_socket_vmnet_transport import require_documented_transport


def qemu_command(vm_name: str, netdev: str) -> str:
    return f"qemu-system-aarch64 -netdev {netdev} /vagrant/{vm_name}/.vagrant/machine.img"


def test_accepts_documented_fd_transport_for_every_vm():
    commands = [
        qemu_command("caldera", "socket,id=net1,fd=3"),
        qemu_command("attacker", "socket,id=net1,fd=3"),
    ]

    selected = require_documented_transport(["caldera", "attacker"], commands)

    assert set(selected) == {"caldera", "attacker"}


def test_rejects_stream_transport_even_when_qemu_supports_it():
    commands = [qemu_command("caldera", "stream,id=net1,server=off")]

    with pytest.raises(RuntimeError, match="stream transport"):
        require_documented_transport(["caldera"], commands)


def test_rejects_missing_vm_process():
    with pytest.raises(RuntimeError, match="found 0"):
        require_documented_transport(["caldera"], [])
