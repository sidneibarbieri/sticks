from __future__ import annotations

import io
import hashlib
import tarfile
from pathlib import Path

import pytest

from scripts.public_tree_manifest import write_manifest
from scripts import screen_typed_evidence_privacy as privacy_screen
from scripts.screen_typed_evidence_privacy import (
    REVIEWED_REFERENCE_SECRET_FIXTURES,
    screen_archive,
)


def make_archive(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for campaign in ("c0010", "c0026"):
            directory = tarfile.TarInfo(campaign)
            directory.type = tarfile.DIRTYPE
            archive.addfile(directory)
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))


def screen_with_manifest(archive: Path, reference: Path):
    write_manifest(reference, reference / "PUBLIC_TREE_SHA256.json")
    return screen_archive(archive, reference)


def test_known_public_reference_is_bound_to_both_exact_byte_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    (reference / "src").mkdir(parents=True)
    (reference / "src/example.py").write_bytes(b"safe fixture\n")
    manifest_path = reference / "PUBLIC_TREE_SHA256.json"
    write_manifest(reference, manifest_path)
    make_archive(archive, {"c0010/workspace/src/example.py": b"safe fixture\n"})
    monkeypatch.setattr(
        privacy_screen,
        "KNOWN_PUBLIC_ARCHIVE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        privacy_screen,
        "KNOWN_PUBLIC_REFERENCE_MANIFEST_SHA256",
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )

    result = screen_archive(archive, known_reference_manifest=manifest_path)

    assert result.passed
    assert result.scopes == {"workspace_unchanged": 1}

    with pytest.raises(ValueError, match="exactly one"):
        screen_archive(archive, reference, known_reference_manifest=manifest_path)
    with pytest.raises(ValueError, match="exactly one"):
        screen_archive(archive)
    with pytest.raises(FileNotFoundError):
        screen_archive(tmp_path / "missing.tar.gz", known_reference_manifest=manifest_path)


def test_known_public_reference_rejects_modified_archive_or_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    reference.mkdir()
    manifest_path = reference / "PUBLIC_TREE_SHA256.json"
    write_manifest(reference, manifest_path)
    make_archive(archive, {"c0010/evidence/run.txt": b"safe"})
    monkeypatch.setattr(
        privacy_screen,
        "KNOWN_PUBLIC_ARCHIVE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        privacy_screen,
        "KNOWN_PUBLIC_REFERENCE_MANIFEST_SHA256",
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )

    archive.write_bytes(archive.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Typed archive differs"):
        screen_archive(archive, known_reference_manifest=manifest_path)

    monkeypatch.setattr(
        privacy_screen,
        "KNOWN_PUBLIC_ARCHIVE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="reference manifest differs"):
        screen_archive(archive, known_reference_manifest=manifest_path)


def test_bound_reference_must_match_both_sealed_workspaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = tmp_path / "reference"
    reference.mkdir()
    (reference / "example.txt").write_bytes(b"safe fixture")
    manifest_path = reference / "PUBLIC_TREE_SHA256.json"
    write_manifest(reference, manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    archive = tmp_path / "evidence.tar.gz"
    files = {
        f"{campaign}/workspace/PUBLIC_TREE_SHA256.json": manifest_bytes
        for campaign in ("c0010", "c0026")
    }
    files.update({
        f"{campaign}/workspace/example.txt": b"safe fixture"
        for campaign in ("c0010", "c0026")
    })
    make_archive(archive, files)
    verified: list[Path] = []
    monkeypatch.setattr(
        privacy_screen, "verify_archive", lambda path, _campaigns: verified.append(path)
    )

    result = screen_archive(archive, bound_reference_manifest=manifest_path)

    assert result.passed
    assert verified == [archive]
    assert result.scopes == {"workspace_generated": 2, "workspace_unchanged": 2}

    manifest_path.write_bytes(manifest_bytes + b" ")
    with pytest.raises(ValueError, match="differs from the sealed run source"):
        screen_archive(archive, bound_reference_manifest=manifest_path)


def test_screen_accepts_lab_paths_but_requires_manual_review(tmp_path: Path) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    reference.mkdir()
    make_archive(archive, {"c0010/evidence/log.txt": b"/home/ubuntu /private/tmp/sticks-run"})

    result = screen_with_manifest(archive, reference)

    assert result.passed
    assert result.lab_home_references == 1
    assert result.generic_temp_references == 1
    assert result.scopes == {"run_evidence": 1}


def test_screen_rejects_new_identifiers_without_echoing_values(tmp_path: Path) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    reference.mkdir()
    make_archive(
        archive,
        {"c0026/evidence/log.txt": b"someone@example.org /home/operator /Users/operator"},
    )

    result = screen_with_manifest(archive, reference)

    assert not result.passed
    assert result.findings == {"email": 1, "mac_home": 1, "unknown_linux_home": 1}
    assert "operator" not in str(result)


def test_screen_rejects_source_url_in_unchanged_workspace(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "reference"
    reference.mkdir()
    source = reference / "PROVENANCE.md"
    source.write_text("https://github.com/reviewername/example\n")
    archive = tmp_path / "evidence.tar.gz"
    make_archive(
        archive,
        {
            "c0010/workspace/PROVENANCE.md": source.read_bytes(),
            "c0026/workspace/PROVENANCE.md": source.read_bytes(),
        },
    )

    result = screen_with_manifest(archive, reference)

    assert not result.passed
    assert result.findings == {"source_repository_url": 2}
    assert result.scopes == {"workspace_unchanged": 2}
    assert "reviewername" not in str(result)


def test_screen_accepts_anonymous_provenance(tmp_path: Path) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    reference.mkdir()
    source = reference / "PROVENANCE.md"
    source.write_text("Source migration recorded in the private ledger.\n")
    make_archive(archive, {"c0010/workspace/PROVENANCE.md": source.read_bytes()})

    result = screen_with_manifest(archive, reference)

    assert result.passed


def test_screen_rejects_unreviewed_reference_secret_markers(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    (reference / "src").mkdir(parents=True)
    fixture = b"-----BEGIN " + b"RSA PRIVATE KEY-----\nplaceholder...\n"
    (reference / "src/fixture.txt").write_bytes(fixture)
    make_archive(archive, {"c0010/workspace/src/fixture.txt": fixture})

    result = screen_with_manifest(archive, reference)

    assert not result.passed
    assert result.findings == {"unreviewed_reference_secret_material": 1}
    assert result.reference_secret_material_hits == 1
    assert result.scopes == {"workspace_unchanged": 1}


def test_screen_accepts_exact_reviewed_reference_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    (reference / "src").mkdir(parents=True)
    fixture = b"-----BEGIN " + b"RSA PRIVATE KEY-----\nplaceholder...\n"
    (reference / "src/fixture.txt").write_bytes(fixture)
    monkeypatch.setitem(
        REVIEWED_REFERENCE_SECRET_FIXTURES,
        "src/fixture.txt",
        (hashlib.sha256(fixture).hexdigest(), 1),
    )
    make_archive(archive, {"c0010/workspace/src/fixture.txt": fixture})

    result = screen_with_manifest(archive, reference)

    assert result.passed
    assert result.reference_secret_material_hits == 1


def test_screen_rejects_lab_profile_private_key_even_if_reviewed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    profile = reference / "lab/sut_profiles/0.lateral_test.yml"
    profile.parent.mkdir(parents=True)
    private_key_header = b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----"
    fixture = b"content: |\n  " + private_key_header + b"\n  placeholder\n"
    profile.write_bytes(fixture)
    monkeypatch.setitem(
        REVIEWED_REFERENCE_SECRET_FIXTURES,
        "lab/sut_profiles/0.lateral_test.yml",
        (hashlib.sha256(fixture).hexdigest(), 1),
    )
    make_archive(
        archive,
        {"c0010/workspace/lab/sut_profiles/0.lateral_test.yml": fixture},
    )

    result = screen_with_manifest(archive, reference)

    assert not result.passed
    assert result.findings == {"lab_profile_private_key": 1}
    assert result.reference_secret_material_hits == 1


def test_screen_reports_credential_patterns_in_unchanged_reference(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    (reference / "src").mkdir(parents=True)
    fixture = (
        b'password="sample-password"\n'
        b"Weak credentials applied: fixture_user:sample-password\n"
    )
    (reference / "src/fixture.txt").write_bytes(fixture)
    make_archive(archive, {"c0010/workspace/src/fixture.txt": fixture})

    result = screen_with_manifest(archive, reference)

    assert result.passed
    assert result.reference_secret_assignment_hits == 1
    assert result.reference_logged_credential_pair_hits == 1
    assert "sample-password" not in str(result)


def test_screen_rejects_embedded_caldera_password_in_unchanged_runner(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    runner = reference / "measurement/sut/scripts/run_campaign.py"
    runner.parent.mkdir(parents=True)
    fixture = b'PASSWORD = "synthetic-lab-secret"\n'
    runner.write_bytes(fixture)
    make_archive(
        archive,
        {"c0010/workspace/measurement/sut/scripts/run_campaign.py": fixture},
    )

    result = screen_with_manifest(archive, reference)

    assert not result.passed
    assert result.findings == {"legacy_runner_embedded_secret": 1}
    assert "synthetic-lab-secret" not in str(result)


def test_screen_accepts_environment_lookup_in_unchanged_runner(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    runner = reference / "measurement/sut/scripts/run_campaign.py"
    runner.parent.mkdir(parents=True)
    fixture = b'password = os.environ["CALDERA_PASSWORD"]\n'
    runner.write_bytes(fixture)
    make_archive(
        archive,
        {"c0010/workspace/measurement/sut/scripts/run_campaign.py": fixture},
    )

    result = screen_with_manifest(archive, reference)

    assert result.passed
    assert result.reference_secret_assignment_hits == 1


def test_screen_rejects_literal_that_looks_like_environment_lookup(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    runner = reference / "measurement/sut/scripts/run_campaign.py"
    runner.parent.mkdir(parents=True)
    fixture = b'password = "os.environ.NOT_A_LOOKUP"\n'
    runner.write_bytes(fixture)
    make_archive(
        archive,
        {"c0010/workspace/measurement/sut/scripts/run_campaign.py": fixture},
    )

    result = screen_with_manifest(archive, reference)

    assert result.findings == {"legacy_runner_embedded_secret": 1}


def test_screen_rejects_embedded_caldera_api_key_in_unchanged_tool(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    tool = reference / "scripts/tools/load_ability.py"
    tool.parent.mkdir(parents=True)
    fixture = b'API_KEY = "synthetic-test-key"\n'
    tool.write_bytes(fixture)
    make_archive(
        archive,
        {"c0010/workspace/scripts/tools/load_ability.py": fixture},
    )

    result = screen_with_manifest(archive, reference)

    assert result.findings == {"caldera_tool_embedded_secret": 1}


def test_screen_rejects_secret_material_in_changed_workspace(tmp_path: Path) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    (reference / "src").mkdir(parents=True)
    (reference / "src/fixture.txt").write_bytes(b"safe")
    make_archive(
        archive,
        {
            "c0010/workspace/src/fixture.txt": (
                b"-----BEGIN " + b"RSA PRIVATE KEY-----"
            )
        },
    )

    result = screen_with_manifest(archive, reference)

    assert not result.passed
    assert result.findings == {"secret_material": 1}
    assert result.scopes == {"workspace_changed": 1}


def test_screen_rejects_logged_credential_pair(tmp_path: Path) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    reference.mkdir()
    make_archive(
        archive,
        {"c0010/execution.log": b"[ok] Weak credentials applied: fixture_user:secret-value"},
    )

    result = screen_with_manifest(archive, reference)

    assert not result.passed
    assert result.findings == {"logged_credential_pair": 1}
    assert "secret-value" not in str(result)


def test_screen_accepts_redacted_credential_status(tmp_path: Path) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    reference.mkdir()
    make_archive(
        archive,
        {"c0010/execution.log": b"[ok] Weak credentials applied for user fixture_user"},
    )

    result = screen_with_manifest(archive, reference)

    assert result.passed


def test_screen_does_not_trust_host_runtime_output_as_reference(tmp_path: Path) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    (reference / "results").mkdir(parents=True)
    output = b"host-specific timing"
    (reference / "results/enumeration_scaling_timing.json").write_bytes(output)
    make_archive(
        archive,
        {"c0010/workspace/results/enumeration_scaling_timing.json": output},
    )

    result = screen_with_manifest(archive, reference)

    assert result.scopes == {"workspace_generated": 1}


def test_screen_rejects_modified_reference_tree(tmp_path: Path) -> None:
    archive = tmp_path / "evidence.tar.gz"
    reference = tmp_path / "reference"
    reference.mkdir()
    (reference / "known.txt").write_bytes(b"frozen")
    write_manifest(reference, reference / "PUBLIC_TREE_SHA256.json")
    (reference / "known.txt").write_bytes(b"modified")
    make_archive(archive, {"c0010/workspace/known.txt": b"frozen"})

    with pytest.raises(RuntimeError, match="public tree integrity failure"):
        screen_archive(archive, reference)
