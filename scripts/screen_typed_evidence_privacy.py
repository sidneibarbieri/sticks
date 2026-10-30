#!/usr/bin/env python3
"""Screen changed bytes in a typed-QEMU archive before private review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(PROJECT_ROOT / "src"), str(PROJECT_ROOT))

from scripts.caldera_runner_secret_policy import (  # noqa: E402
    CALDERA_TOOL_SOURCES,
    LEGACY_CALDERA_RUNNERS,
    literal_credential_assignment_count,
)
from scripts.public_tree_manifest import verify_manifest  # noqa: E402
from scripts.verify_typed_evidence_archive import (  # noqa: E402
    CAMPAIGN_DIRECTORIES,
    SERIES,
    validate_members,
    verify_archive,
)


EMAIL = re.compile(rb"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
GITHUB_SOURCE_URL = re.compile(rb"(?i)https?://(?:www\.)?github\.com/[A-Za-z0-9_.-]+")
MAC_HOME = re.compile(rb"/Users/[^/\s]+")
LINUX_HOME = re.compile(rb"/home/([^/\s]+)")
TEMP_PATH = re.compile(rb"/private/tmp/([^/\s]+)")
TENANT_GUID = re.compile(
    rb"(?i)\b(?:tenant|customer|client|account|org)[_-]?(?:id|guid)\b"
    rb"[^\r\n]{0,32}\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    rb"[0-9a-f]{4}-[0-9a-f]{12}\b"
)
SECRET_ASSIGNMENT = re.compile(
    rb"(?i)\b(?:password|passphrase|api[_-]?key|access[_-]?token|"
    rb"client[_-]?secret)\b\s*[=:]\s*['\"]?[A-Za-z0-9_./+@-]{8,}"
)
LOGGED_CREDENTIAL_PAIR = re.compile(
    rb"(?i)\bweak credentials applied:\s*[A-Za-z0-9._-]+:[^\s]+"
)
SECRET_MATERIAL = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(rb"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\."
               rb"[A-Za-z0-9_-]{10,}\b"),
)
LAB_USERS = {b"attacker", b"ubuntu"}


# These exact digests belong to the sealed historical QEMU workspaces. They
# contain non-functional credential-shaped fixtures, not live credentials.
# New workspaces use non-secret placeholders and must not extend this map.
REVIEWED_REFERENCE_SECRET_FIXTURES: dict[str, tuple[str, int]] = {
    "src/executors/realistic_data_generator.py": (
        "fbb7cc31186a9dea3f2923fbecb538b3b457beaed7291618067b839e37aafd59", 3
    ),
    "lab/vagrant/shared/target.sh": (
        "53bf1f367f13cbb341d764c467325c58e1bb87bdcb3904aba4fa93badcfc6167", 1
    ),
    "tests/test_screen_typed_evidence_privacy.py": (
        "f3789a71293f267c3a7f1505f360d9e5e7f4c0e8904f8e86689f161f73320d7a", 3
    ),
    "tests/test_public_surface_metrics.py": (
        "9d763d31052ce7a525a1047e3aad1c89b98ed6c71c9a423c4362a479de5ec239", 1
    ),
}
KNOWN_PUBLIC_ARCHIVE_SHA256 = (
    "01733cdf57de72b0970f323e0265afb41b9b13613e84c13946216969b1c65ae5"
)
KNOWN_PUBLIC_REFERENCE_MANIFEST_SHA256 = (
    "134fba3cec5b6c65a28c498d37b8a66c1362704c7ce31a806bc7f81c9b4f9a1d"
)


@dataclass(frozen=True)
class ScreenResult:
    members: int
    scopes: dict[str, int]
    findings: dict[str, int]
    reference_secret_material_hits: int
    reference_secret_assignment_hits: int
    reference_logged_credential_pair_hits: int
    lab_home_references: int
    generic_temp_references: int

    @property
    def passed(self) -> bool:
        return not self.findings


def _scope(member_name: str, data: bytes, reference_files: dict) -> str:
    if "/workspace/" not in member_name:
        return "run_evidence"
    relative = member_name.split("/workspace/", 1)[1]
    reference = reference_files.get(relative)
    if reference is None:
        return "workspace_generated"
    if hashlib.sha256(data).hexdigest() == reference["sha256"]:
        return "workspace_unchanged"
    return "workspace_changed"


def _known_reference_files(archive_path: Path, manifest_path: Path) -> dict:
    with archive_path.open("rb") as source:
        archive_digest = hashlib.file_digest(source, "sha256").hexdigest()
    manifest_bytes = manifest_path.read_bytes()
    if archive_digest != KNOWN_PUBLIC_ARCHIVE_SHA256:
        raise ValueError("Typed archive differs from the known public snapshot")
    if hashlib.sha256(manifest_bytes).hexdigest() != KNOWN_PUBLIC_REFERENCE_MANIFEST_SHA256:
        raise ValueError("Typed reference manifest differs from the known public snapshot")
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema_version") != "1" or not isinstance(manifest.get("files"), dict):
        raise ValueError("Known typed reference manifest has an invalid schema")
    return manifest["files"]


def _bound_reference_files(
    archive_path: Path,
    manifest_path: Path,
    campaign_directories: tuple[str, ...] = CAMPAIGN_DIRECTORIES,
) -> dict:
    verify_archive(archive_path, campaign_directories)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema_version") != "1" or not isinstance(manifest.get("files"), dict):
        raise ValueError("Bound typed reference manifest has an invalid schema")
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        validate_members(members, campaign_directories)
        for campaign in campaign_directories:
            member = archive.getmember(f"{campaign}/workspace/PUBLIC_TREE_SHA256.json")
            source = archive.extractfile(member)
            if source is None or source.read() != manifest_bytes:
                raise ValueError("Bound typed reference differs from the sealed run source")
    return manifest["files"]


def screen_archive(
    archive_path: Path,
    reference_root: Path | None = None,
    *,
    known_reference_manifest: Path | None = None,
    bound_reference_manifest: Path | None = None,
    campaign_directories: tuple[str, ...] = CAMPAIGN_DIRECTORIES,
) -> ScreenResult:
    if sum(reference is not None for reference in (
        reference_root, known_reference_manifest, bound_reference_manifest
    )) != 1:
        raise ValueError("Select exactly one typed evidence reference")
    reference_files = (
        _known_reference_files(archive_path, known_reference_manifest)
        if known_reference_manifest is not None
        else _bound_reference_files(
            archive_path, bound_reference_manifest, campaign_directories
        )
        if bound_reference_manifest is not None
        else verify_manifest(
            reference_root, reference_root / "PUBLIC_TREE_SHA256.json"
        )["files"]
    )
    scopes: Counter[str] = Counter()
    findings: Counter[str] = Counter()
    lab_home_references = 0
    generic_temp_references = 0
    reference_secret_material_hits = 0
    reference_secret_assignment_hits = 0
    reference_logged_credential_pair_hits = 0
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        validate_members(members, campaign_directories)
        for member in members:
            if not member.isfile():
                continue
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Archive member has no data")
            data = source.read()
            scope = _scope(member.name, data, reference_files)
            scopes[scope] += 1
            if member.name.endswith("/workspace/PROVENANCE.md"):
                findings["source_repository_url"] += len(
                    GITHUB_SOURCE_URL.findall(data)
                )
            secret_material_hits = sum(
                len(pattern.findall(data)) for pattern in SECRET_MATERIAL
            )
            if scope == "workspace_unchanged":
                reference_secret_material_hits += secret_material_hits
                assignment_hits = len(SECRET_ASSIGNMENT.findall(data))
                reference_secret_assignment_hits += assignment_hits
                reference_logged_credential_pair_hits += len(
                    LOGGED_CREDENTIAL_PAIR.findall(data)
                )
                relative = member.name.split("/workspace/", 1)[1]
                if relative in LEGACY_CALDERA_RUNNERS:
                    findings["legacy_runner_embedded_secret"] += (
                        literal_credential_assignment_count(data)
                    )
                elif relative in CALDERA_TOOL_SOURCES:
                    findings["caldera_tool_embedded_secret"] += (
                        literal_credential_assignment_count(data)
                    )
                if relative.startswith("lab/sut_profiles/") and SECRET_MATERIAL[0].search(data):
                    findings["lab_profile_private_key"] += 1
                if secret_material_hits:
                    reviewed = REVIEWED_REFERENCE_SECRET_FIXTURES.get(relative)
                    if reviewed != (hashlib.sha256(data).hexdigest(), secret_material_hits):
                        findings["unreviewed_reference_secret_material"] += secret_material_hits
                continue
            findings["secret_material"] += secret_material_hits
            findings["email"] += len(EMAIL.findall(data))
            findings["mac_home"] += len(MAC_HOME.findall(data))
            findings["tenant_guid"] += len(TENANT_GUID.findall(data))
            findings["secret_assignment"] += len(SECRET_ASSIGNMENT.findall(data))
            findings["logged_credential_pair"] += len(LOGGED_CREDENTIAL_PAIR.findall(data))
            for user in LINUX_HOME.findall(data):
                if user in LAB_USERS:
                    lab_home_references += 1
                else:
                    findings["unknown_linux_home"] += 1
            for component in TEMP_PATH.findall(data):
                if component.startswith(b"sticks-"):
                    generic_temp_references += 1
                else:
                    findings["other_temp_path"] += 1
    return ScreenResult(
        members=sum(scopes.values()),
        scopes=dict(scopes),
        findings={name: count for name, count in findings.items() if count},
        reference_secret_material_hits=reference_secret_material_hits,
        reference_secret_assignment_hits=reference_secret_assignment_hits,
        reference_logged_credential_pair_hits=reference_logged_credential_pair_hits,
        lab_home_references=lab_home_references,
        generic_temp_references=generic_temp_references,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    reference = parser.add_mutually_exclusive_group(required=True)
    reference.add_argument("--reference-root", type=Path)
    reference.add_argument("--known-reference-manifest", type=Path)
    reference.add_argument("--bound-reference-manifest", type=Path)
    parser.add_argument("--series", choices=sorted(SERIES), default="qemu")
    args = parser.parse_args()
    result = screen_archive(
        args.archive,
        args.reference_root,
        known_reference_manifest=args.known_reference_manifest,
        bound_reference_manifest=args.bound_reference_manifest,
        campaign_directories=SERIES[args.series],
    )
    print(json.dumps({
        "screen_pass": result.passed,
        "manual_semantic_review_required": True,
        "members": result.members,
        "scopes": result.scopes,
        "findings": result.findings,
        "reference_secret_material_hits": result.reference_secret_material_hits,
        "reference_secret_assignment_hits": result.reference_secret_assignment_hits,
        "reference_logged_credential_pair_hits": result.reference_logged_credential_pair_hits,
        "lab_home_references": result.lab_home_references,
        "generic_temp_references": result.generic_temp_references,
    }, indent=2, sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
