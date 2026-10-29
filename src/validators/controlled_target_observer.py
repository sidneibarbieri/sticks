"""Validate read-only observations of controlled Linux target effects."""

import hashlib
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field


class ObserverRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FixtureDeclaration(ObserverRecord):
    path: str
    content: str
    owner: str
    permissions: str = "644"


class ObservedFixture(ObserverRecord):
    path: str
    sha256: str
    owner: str
    mode: str
    owner_read_exit_code: int


class TargetObservation(ObserverRecord):
    hostname: str = Field(min_length=1)
    boot_id: str = Field(min_length=1)
    files: list[ObservedFixture]
    payload_sha256: str
    server_log: str
    mac_addresses: dict[str, str]


def declaration_by_path(fixtures: list[FixtureDeclaration]) -> dict[str, FixtureDeclaration]:
    """Reject empty, duplicate, and non-absolute fixture declarations."""
    if not fixtures:
        raise ValueError("Fixture declaration must be nonempty")
    declarations = {fixture.path: fixture for fixture in fixtures}
    if len(declarations) != len(fixtures):
        raise ValueError("Fixture paths must be unique")
    for fixture in fixtures:
        path = PurePosixPath(fixture.path)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe fixture path: {fixture.path}")
        if not fixture.owner or fixture.owner.startswith("-"):
            raise ValueError("Fixture owner must name an account")
        int(fixture.permissions, 8)
    return declarations


def fixture_errors(
    declarations: dict[str, FixtureDeclaration], observation: TargetObservation,
) -> list[str]:
    errors = []
    paths = [fixture.path for fixture in observation.files]
    if len(set(paths)) != len(paths):
        errors.append("duplicate_observed_path")
    if set(paths) != set(declarations):
        errors.append("fixture_set_mismatch")
    for observed in observation.files:
        expected = declarations.get(observed.path)
        if expected is None:
            continue
        comparisons = {
            "sha256": hashlib.sha256(expected.content.encode()).hexdigest(),
            "owner": expected.owner,
            "mode": format(int(expected.permissions, 8), "o"),
            "owner_read_exit_code": 0,
        }
        errors.extend(
            f"{observed.path}: {field} mismatch"
            for field, value in comparisons.items() if getattr(observed, field) != value
        )
    return errors


def browser_errors(fixtures: list[FixtureDeclaration], report: str) -> list[str]:
    browser_fixtures = [
        fixture for fixture in fixtures
        if any(marker in PurePosixPath(fixture.path).parts
               for marker in (".mozilla", "google-chrome", "chromium"))
    ]
    owners = {fixture.owner for fixture in browser_fixtures}
    if len(owners) != 1 or "root" in owners:
        raise ValueError("Browser observation requires one declared non-root owner")
    lines = set(report.splitlines())
    owner = next(iter(owners))
    errors = []
    identities = {line for line in lines if line.startswith("[identity]")}
    if identities != {f"[identity] {owner}"}:
        errors.append("browser_identity_mismatch")
    if any(fixture.path not in lines for fixture in browser_fixtures):
        errors.append("browser_declared_path_missing")
    return errors


def validate_observation(
    fixtures: list[FixtureDeclaration], observation: TargetObservation, browser_report: str,
) -> list[str]:
    """Check fixtures, benign loopback transfer, browser binding, and NIC types.

    This does not certify unrelated technique effects or historical fidelity.
    """
    declarations = declaration_by_path(fixtures)
    errors = fixture_errors(declarations, observation)
    errors.extend(browser_errors(fixtures, browser_report))
    payload_hash = hashlib.sha256(b"#!/bin/sh\necho STICKS benign payload\n").hexdigest()
    if (observation.payload_sha256 != payload_hash
            or '"GET /payload.sh HTTP/1.1" 200' not in observation.server_log):
        errors.append("controlled_loopback_transfer_mismatch")
    if len(observation.mac_addresses) < 2 or any(
        len(address.split(":")) != 6 or any(
            len(octet) != 2 or any(character not in "0123456789abcdefABCDEF"
                                   for character in octet)
            for octet in address.split(":")
        ) for address in observation.mac_addresses.values()
    ):
        errors.append("network_mac_observation_incomplete")
    return errors
