from __future__ import annotations

import pytest

from runners.prepared_runtime_attestation import PreparedGuestInventory


def _inventory(**overrides: object) -> PreparedGuestInventory:
    fields: dict[str, object] = {
        "schema_version": "c0045-prepared-guest-inventory/v1",
        "role": "caldera",
        "hostname": "caldera-server",
        "os_release": ("22.04", "ubuntu"),
        "packages": (),
        "python_packages": (),
        "caldera_revision": "a" * 40,
        "caldera_submodules": (),
        "active_services": ("active",),
        "private_key_paths": (),
        "vagrant_transport_fingerprint": "SHA256:1M4RzhMyWuFS/86uPY/ce2prh/dVTHW7iD2RhpquOZA",
    }
    fields.update(overrides)
    return PreparedGuestInventory(**fields)


def test_prepared_inventory_rejects_private_key_paths() -> None:
    with pytest.raises(ValueError, match="private-key"):
        _inventory(private_key_paths=("/home/attacker/.ssh/id_rsa",))


def test_prepared_caldera_inventory_requires_revision() -> None:
    with pytest.raises(ValueError, match="lacks a pinned revision"):
        _inventory(caldera_revision=None)


def test_non_caldera_inventory_cannot_claim_caldera_revision() -> None:
    with pytest.raises(ValueError, match="Only the Caldera role"):
        _inventory(role="attacker")


def test_prepared_inventory_accepts_secret_free_caldera() -> None:
    assert _inventory().role == "caldera"
