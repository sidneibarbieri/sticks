#!/usr/bin/env python3
"""Screen every JSON member of a C0045 series archive for release residue."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(PROJECT_ROOT / "src"), str(PROJECT_ROOT))

from scripts import screen_typed_evidence_privacy as typed_screen  # noqa: E402
from scripts.verify_c0045_effect_series_archive import verify_archive  # noqa: E402


IPV4 = re.compile(rb"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
URL = re.compile(rb"(?i)\b(?:https?|ssh)://")
TENANT_FIELD = re.compile(r"(?i)(?:tenant|customer|client|account|org)[_-]?(?:id|guid)$")
SECRET_FIELD = re.compile(r"(?i)(?:password|passphrase|api[_-]?key|access[_-]?token|client[_-]?secret)$")
PATTERNS = {
    "email": typed_screen.EMAIL,
    "mac_home": typed_screen.MAC_HOME,
    "linux_home": typed_screen.LINUX_HOME,
    "temp_path": typed_screen.TEMP_PATH,
    "tenant_guid": typed_screen.TENANT_GUID,
    "secret_assignment": typed_screen.SECRET_ASSIGNMENT,
    "logged_credential_pair": typed_screen.LOGGED_CREDENTIAL_PAIR,
    "ipv4": IPV4,
    "url": URL,
}


@dataclass(frozen=True)
class PrivacyScreenResult:
    archive_sha256: str
    json_members: int
    findings: dict[str, int]

    @property
    def passed(self) -> bool:
        return not self.findings


def _screen_string(value: str, findings: Counter[str]) -> None:
    encoded = value.encode("utf-8")
    for name, pattern in PATTERNS.items():
        findings[name] += len(pattern.findall(encoded))
    for pattern in typed_screen.SECRET_MATERIAL:
        findings["secret_material"] += len(pattern.findall(encoded))


def _screen_value(value: object, findings: Counter[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object contains a non-string key")
            if child not in (None, "", [], {}):
                if TENANT_FIELD.search(key):
                    findings["tenant_field"] += 1
                if SECRET_FIELD.search(key):
                    findings["secret_field"] += 1
            _screen_string(key, findings)
            _screen_value(child, findings)
    elif isinstance(value, list):
        for child in value:
            _screen_value(child, findings)
    elif isinstance(value, str):
        _screen_string(value, findings)


def screen_archive(
    archive_path: Path, series_path: Path | None = None
) -> PrivacyScreenResult:
    audit = verify_archive(archive_path, series_path)
    findings: Counter[str] = Counter()
    json_members = 0
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            if not member.name.endswith(".json"):
                raise ValueError("C0045 archive contains a non-JSON file")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("C0045 archive member has no data")
            with source:
                document = json.load(source)
            _screen_value(document, findings)
            json_members += 1
    return PrivacyScreenResult(
        archive_sha256=audit.archive_sha256,
        json_members=json_members,
        findings={name: count for name, count in findings.items() if count},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--series-path", type=Path, default=None)
    args = parser.parse_args()
    result = screen_archive(args.archive, args.series_path)
    print(json.dumps({
        "archive_sha256": result.archive_sha256,
        "json_members": result.json_members,
        "screen_pass": result.passed,
        "manual_semantic_review_required": True,
        "findings": result.findings,
    }, indent=2, sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
