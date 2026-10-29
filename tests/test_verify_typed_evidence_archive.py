"""The archive verifier rejects unsafe payloads before extraction."""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from scripts import verify_typed_evidence_archive as verifier
from scripts.audit_typed_campaign_outcomes import CampaignOutcome
from scripts.render_typed_campaign_outcomes_tex import render_tex


def test_verifier_script_is_directly_invocable() -> None:
    result = subprocess.run(
        [sys.executable, str(Path(verifier.__file__)), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Verify a private typed-QEMU evidence archive" in result.stdout


def member(name: str, *, directory: bool = False, size: int = 0) -> tarfile.TarInfo:
    entry = tarfile.TarInfo(name)
    entry.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    entry.size = size
    return entry


def test_rejects_appledouble_and_traversal() -> None:
    roots = [member("c0010", directory=True), member("c0026", directory=True)]
    for unsafe in ("._c0010", "c0010/._receipt", "c0010/../escape"):
        with pytest.raises(ValueError, match="unsafe or unexpected path"):
            verifier.validate_members([*roots, member(unsafe)])


def test_rejects_symlink() -> None:
    linked = member("c0010/linked")
    linked.type = tarfile.SYMTYPE
    with pytest.raises(ValueError, match="link or special file"):
        verifier.validate_members(
            [member("c0010", directory=True), member("c0026", directory=True), linked]
        )


def test_rejects_oversized_file() -> None:
    with pytest.raises(ValueError, match="oversized file"):
        verifier.validate_members(
            [
                member("c0010", directory=True),
                member("c0026", directory=True),
                member("c0010/huge", size=verifier.MAX_FILE_BYTES + 1),
            ]
        )


def test_extracts_only_validated_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "evidence.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        for name in verifier.CAMPAIGN_DIRECTORIES:
            archive.addfile(member(name, directory=True))
            content = name.encode("utf-8")
            archive.addfile(
                member(f"{name}/receipt.txt", size=len(content)), io.BytesIO(content)
            )
    destination = tmp_path / "extracted"
    destination.mkdir()
    with tarfile.open(archive_path, mode="r:gz") as archive:
        verifier.extract_members(archive, destination)
    assert (destination / "c0010/receipt.txt").read_text() == "c0010"
    assert (destination / "c0026/receipt.txt").read_text() == "c0026"


def typed_outcomes() -> list[CampaignOutcome]:
    return [
        CampaignOutcome(
            campaign_id=campaign_id,
            run_id=campaign_id,
            source_tree_sha256="a" * 64,
            receipt_sha256="b" * 64,
            observed_target=target,
            observed_controller=controller,
            simulated=simulated,
            failed=0,
            total=target + controller + simulated,
        )
        for campaign_id, target, controller, simulated in (
            ("0.c0010", 1, 4, 4),
            ("0.c0026", 5, 0, 1),
        )
    ]


def test_paper_outcomes_must_match_sealed_archive(tmp_path: Path) -> None:
    paper_file = tmp_path / "typed_campaign_outcomes.tex"
    outcomes = typed_outcomes()
    paper_file.write_text(render_tex(outcomes), encoding="utf-8")

    verifier.verify_paper_outcomes(outcomes, paper_file)

    paper_file.write_text(
        render_tex(outcomes).replace(
            "\\coldCollectionTarget}{5}", "\\coldCollectionTarget}{6}"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="disagree with sealed receipts"):
        verifier.verify_paper_outcomes(outcomes, paper_file)


def test_paper_outcomes_file_is_required(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        verifier.verify_paper_outcomes(typed_outcomes(), tmp_path / "missing.tex")
