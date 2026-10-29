"""Paper-facing QEMU numbers remain bound to the audited run population."""

from __future__ import annotations

import pytest

from scripts.audit_typed_campaign_outcomes import CampaignOutcome
from scripts.render_typed_campaign_outcomes_tex import render_tex


def outcome(
    campaign_id: str, target: int, controller: int, simulated: int
) -> CampaignOutcome:
    return CampaignOutcome(
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


def test_render_preserves_locus_and_simulation() -> None:
    rendered = render_tex([outcome("0.c0010", 1, 4, 4), outcome("0.c0026", 5, 0, 1)])
    assert "\\newcommand{\\coldInfrastructureTarget}{1}" in rendered
    assert "\\newcommand{\\coldInfrastructureController}{4}" in rendered
    assert "\\newcommand{\\coldInfrastructureSimulated}{4}" in rendered
    assert "\\newcommand{\\coldCollectionTarget}{5}" in rendered
    assert "\\newcommand{\\coldCollectionSimulated}{1}" in rendered


def test_render_rejects_missing_campaign() -> None:
    with pytest.raises(ValueError, match="exactly C0010 and C0026"):
        render_tex([outcome("0.c0010", 1, 4, 4)])


def test_render_rejects_wrong_population() -> None:
    with pytest.raises(ValueError, match="Unexpected occurrence count"):
        render_tex([outcome("0.c0010", 1, 3, 4), outcome("0.c0026", 5, 0, 1)])


def test_render_rejects_different_source_tree() -> None:
    second = outcome("0.c0026", 5, 0, 1).model_copy(
        update={"source_tree_sha256": "c" * 64}
    )
    with pytest.raises(ValueError, match="share one source tree"):
        render_tex([outcome("0.c0010", 1, 4, 4), second])
