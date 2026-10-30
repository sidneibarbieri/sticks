"""The CALDERA C0026 cycle is a separate typed-evidence series."""

import tarfile

import pytest

from scripts.audit_typed_campaign_outcomes import CampaignOutcome
from scripts.render_typed_campaign_outcomes_tex import render_caldera_tex
from scripts.verify_typed_evidence_archive import SERIES, validate_members
from scripts import verify_typed_evidence_archive as verifier
from scripts import verify_caldera_run_journal as journal
from scripts import reproduce


def outcome(campaign_id: str = "0.c0026", total: int = 6) -> CampaignOutcome:
    return CampaignOutcome(
        campaign_id=campaign_id, run_id="run", source_tree_sha256="s" * 64,
        receipt_sha256="r" * 64, observed_target=total - 1, observed_controller=0,
        simulated=1, failed=0, total=total,
    )


def test_caldera_macros_name_their_receipt_and_counts() -> None:
    tex = render_caldera_tex([outcome()])
    assert f"% 0.c0026 receipt SHA-256: {'r' * 64}" in tex
    assert "\\newcommand{\\calderaTarget}{5}" in tex
    assert "\\newcommand{\\calderaSimulated}{1}" in tex
    assert "\\newcommand{\\calderaFailed}{0}" in tex


@pytest.mark.parametrize("bad", [[outcome("0.c0010", 9)], [outcome(total=7)], [outcome(), outcome()]])
def test_caldera_macros_refuse_other_populations(bad) -> None:
    with pytest.raises(ValueError):
        render_caldera_tex(bad)


def test_caldera_archive_admits_only_its_campaign_root() -> None:
    root = tarfile.TarInfo("c0026")
    root.type = tarfile.DIRTYPE
    validate_members([root], SERIES["caldera"])
    other = tarfile.TarInfo("c0010")
    other.type = tarfile.DIRTYPE
    with pytest.raises(ValueError, match="unexpected path"):
        validate_members([root, other], SERIES["caldera"])


def test_caldera_verification_requires_native_journal(tmp_path, monkeypatch) -> None:
    archive = tmp_path / "series.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        root = tarfile.TarInfo("c0010")
        root.type = tarfile.DIRTYPE
        output.addfile(root)
    monkeypatch.setattr(verifier, "audit_runs", lambda _: [])

    def reject_missing_journal(evidence):
        assert evidence.name == "evidence"
        raise ValueError("No native journal")

    monkeypatch.setattr(journal, "verify_journal", reject_missing_journal)
    with pytest.raises(ValueError, match="No native journal"):
        verifier.verify_archive(archive, SERIES["caldera-c0010"], require_caldera=True)


def test_operational_c0010_series_cannot_relabel_c0026_paper_macros(tmp_path) -> None:
    with pytest.raises(ValueError, match="no registered manuscript"):
        verifier.verify_paper_outcomes([], tmp_path / "unused.tex", "caldera-c0010")


def test_reproduction_screens_and_replays_optional_c0010_archive(tmp_path, monkeypatch) -> None:
    archive = tmp_path / "c0010.tar.gz"
    archive.touch()
    reference = tmp_path / "reference.json"
    commands = []
    monkeypatch.setattr(reproduce, "CALDERA_C0010_EVIDENCE_PATH", archive)
    monkeypatch.setattr(reproduce, "CALDERA_C0010_REFERENCE_PATH", reference)
    monkeypatch.setattr(reproduce, "_run", commands.append)
    reproduce._verify_c0010_caldera_evidence()
    assert len(commands) == 2
    assert "scripts.screen_typed_evidence_privacy" in commands[0]
    assert "--bound-reference-manifest" in commands[0]
    assert "scripts.verify_typed_evidence_archive" in commands[1]
    assert all(command[-1] == "caldera-c0010" or "caldera-c0010" in command for command in commands)
