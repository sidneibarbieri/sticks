"""The CALDERA C0026 cycle is a separate typed-evidence series."""

import tarfile

import pytest

from scripts.audit_typed_campaign_outcomes import CampaignOutcome
from scripts.render_typed_campaign_outcomes_tex import render_caldera_tex
from scripts.verify_typed_evidence_archive import SERIES, validate_members


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
