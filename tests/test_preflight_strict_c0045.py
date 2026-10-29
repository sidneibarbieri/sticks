import socket
import tempfile
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import preflight_strict_c0045 as preflight


def test_preflight_rejects_socket_path_without_listener(tmp_path: Path) -> None:
    socket_path = tmp_path / "socket_vmnet"
    with pytest.raises(RuntimeError, match="absent"):
        preflight._require_live_socket(socket_path)


def test_preflight_accepts_live_socket() -> None:
    with tempfile.TemporaryDirectory(prefix="s-", dir="/tmp") as directory:
        socket_path = Path(directory) / "vmnet"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            listener.listen(1)
            preflight._require_live_socket(socket_path)


@pytest.mark.parametrize("daemon_count", [0, 2])
def test_preflight_rejects_nonunique_socket_vmnet_daemons(
    monkeypatch: pytest.MonkeyPatch, daemon_count: int
) -> None:
    process_listing = "".join(
        f"{index} /opt/homebrew/opt/socket_vmnet/bin/socket_vmnet /tmp/vmnet\n"
        for index in range(daemon_count)
    )
    monkeypatch.setattr(preflight, "_run", lambda *_command: process_listing)

    with pytest.raises(RuntimeError, match="exactly one socket_vmnet daemon"):
        preflight._require_single_socket_vmnet_daemon()


def test_preflight_accepts_one_socket_vmnet_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preflight,
        "_run",
        lambda *_command: "42 /opt/homebrew/opt/socket_vmnet/bin/socket_vmnet /tmp/vmnet\n",
    )

    preflight._require_single_socket_vmnet_daemon()


def test_preflight_checks_the_documented_socket_vmnet_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> None:
        observed["command"] = command
        observed["kwargs"] = kwargs

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)

    preflight._require_documented_socket_vmnet_transport()

    assert observed["command"] == [
        preflight.sys.executable,
        str(preflight.SOCKET_VMNET_TRANSPORT_CHECK),
        "--check",
    ]
    assert observed["kwargs"] == {"check": True, "capture_output": True, "text": True}


def test_preflight_selects_the_box_provider_declared_by_the_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preflight,
        "_run",
        lambda *_command: (
            "perk/ubuntu-2204-arm64  (qemu, 20250702, (arm64))\n"
            "perk/ubuntu-2204-arm64  (libvirt, 20250702, (arm64))\n"
        ),
    )

    assert (
        preflight._installed_box_provider(
            "perk/ubuntu-2204-arm64", "20250702", "qemu"
        )
        == "qemu"
    )


def test_preflight_parses_current_vagrant_box_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preflight,
        "_run",
        lambda *_command: "perk/ubuntu-2204-arm64  (libvirt, 20250702, (arm64))\n",
    )

    assert (
        preflight._installed_box_provider(
            "perk/ubuntu-2204-arm64", "20250702", "libvirt"
        )
        == "libvirt"
    )


def test_preflight_rejects_a_provider_outside_the_frozen_contract() -> None:
    with pytest.raises(RuntimeError, match="expected qemu, found libvirt"):
        preflight._require_declared_provider("libvirt", "qemu")


def test_preflight_requires_pinned_plugin_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preflight, "_run", lambda *_command: "vagrant-qemu (0.6.3, global)\n"
    )

    assert preflight._vagrant_qemu_version() == "0.6.3"


def test_preflight_rechecks_then_reuses_only_an_identical_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = SimpleNamespace(
        provider="qemu",
        minimum_vagrant_qemu_version="0.6.3",
        requirements_lock_sha256="a" * 64,
        prepared_runtime_manifest_sha256="d" * 64,
    )
    image = SimpleNamespace(
        box_name="sticks/c0045-caldera-arm64",
        box_version="1",
        box_provider="libvirt",
        image_fingerprint_sha256="b" * 64,
    )
    runtime = SimpleNamespace(
        images={"caldera": image, "attacker": image, "target-linux-1": image}
    )
    monkeypatch.setattr(preflight, "load_strict_execution_profile", lambda: profile)
    monkeypatch.setattr(
        preflight, "load_prepared_runtime_manifest", lambda _profile: runtime
    )
    monkeypatch.setattr(preflight, "_vagrant_qemu_version", lambda: "0.6.3")
    monkeypatch.setattr(preflight, "_installed_box_provider", lambda *_args: "libvirt")
    monkeypatch.setattr(preflight, "_require_live_socket", lambda _path: None)
    monkeypatch.setattr(preflight, "_require_single_socket_vmnet_daemon", lambda: None)
    monkeypatch.setattr(preflight, "_require_documented_socket_vmnet_transport", lambda: None)
    monkeypatch.setattr(preflight, "_box_directory", lambda *_args: tmp_path)
    monkeypatch.setattr(preflight, "image_tree_sha256", lambda _path: "b" * 64)
    monkeypatch.setattr(preflight, "strict_profile_sha256", lambda: "c" * 64)
    monkeypatch.setattr(preflight, "_run", lambda *_args: "vagrant 2.5.0")

    first = preflight.create_receipt(tmp_path / "output")
    second = preflight.create_receipt(tmp_path / "output")

    assert second == first
    assert (
        first.image_fingerprint_sha256
        == sha256(
            b'{"attacker": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "caldera": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "target-linux-1": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}'
        ).hexdigest()
    )
