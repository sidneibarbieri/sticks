"""Typed, secret-free inventory for one prepared C0045 VM role."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from runners.capability_facts import Identity, ImmutableRecord


class PreparedGuestInventory(ImmutableRecord):
    """Stable runtime facts inspected before a role image is frozen."""

    schema_version: Literal["c0045-prepared-guest-inventory/v1"]
    role: Literal["caldera", "attacker", "target-linux-1"]
    hostname: Identity
    os_release: tuple[Identity, ...] = Field(min_length=1)
    packages: tuple[Identity, ...]
    python_packages: tuple[Identity, ...]
    caldera_revision: Identity | None
    caldera_submodules: tuple[Identity, ...]
    active_services: tuple[Identity, ...]
    private_key_paths: tuple[Identity, ...]
    vagrant_transport_fingerprint: Literal["SHA256:1M4RzhMyWuFS/86uPY/ce2prh/dVTHW7iD2RhpquOZA"]

    @model_validator(mode="after")
    def reject_private_material(self) -> "PreparedGuestInventory":
        if self.private_key_paths:
            raise ValueError("Prepared runtime contains a private-key path")
        if self.role == "caldera" and self.caldera_revision is None:
            raise ValueError("Prepared Caldera runtime lacks a pinned revision")
        if self.role != "caldera" and self.caldera_revision is not None:
            raise ValueError("Only the Caldera role may declare a Caldera revision")
        return self
