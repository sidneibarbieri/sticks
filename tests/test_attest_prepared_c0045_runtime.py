from __future__ import annotations

import pytest

from runners.prepared_runtime_attestation import PreparedGuestInventory
from scripts import attest_prepared_c0045_runtime as attestation


def _inventory(role: str = "attacker") -> PreparedGuestInventory:
    return PreparedGuestInventory(
        schema_version="c0045-prepared-guest-inventory/v1",
        role=role,
        hostname=f"sticks-{role}",
        os_release=("ubuntu", "22.04"),
        packages=("bash=1",),
        python_packages=("pip==1",),
        caldera_revision="a" * 40 if role == "caldera" else None,
        caldera_submodules=() if role != "caldera" else ("a" * 40,),
        active_services=("active",),
        private_key_paths=(),
        vagrant_transport_fingerprint="SHA256:1M4RzhMyWuFS/86uPY/ce2prh/dVTHW7iD2RhpquOZA",
    )


def test_write_inventory_is_idempotent_for_identical_vm(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = _inventory()
    monkeypatch.setattr(attestation, "collect_inventory", lambda role: inventory)

    first = attestation.write_inventory("attacker", tmp_path)
    second = attestation.write_inventory("attacker", tmp_path)

    assert first == second
    assert PreparedGuestInventory.model_validate_json(first.read_bytes()) == inventory


def test_write_inventory_rejects_runtime_drift(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(attestation, "collect_inventory", lambda role: _inventory())
    attestation.write_inventory("attacker", tmp_path)
    monkeypatch.setattr(
        attestation,
        "collect_inventory",
        lambda role: _inventory(role="target-linux-1"),
    )

    with pytest.raises(ValueError, match="differs from current VM"):
        attestation.write_inventory("attacker", tmp_path)
