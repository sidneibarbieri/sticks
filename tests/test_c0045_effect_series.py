"""The post-diagnostic C0045 series must not permit selective cell omission."""

import pytest

from runners.c0045_effect_series import (
    C0045EffectSeries,
    SERIES_V2_PATH,
    load_c0045_effect_series,
)


def test_series_has_five_fresh_boot_blocks_with_all_four_arms() -> None:
    series = load_c0045_effect_series()
    assert len(series.selected_cells) == 20
    assert series.arm_for("b1-treatment") == "treatment"
    assert series.arm_for("b5-controller_only") == "controller_only"
    assert series.prior_treatment_role == "diagnostic_excluded"


def test_series_rejects_missing_or_unselected_cells() -> None:
    series = load_c0045_effect_series()
    with pytest.raises(ValueError, match="frozen schedule"):
        series.arm_for("b6-treatment")
    with pytest.raises(ValueError, match="every arm"):
        C0045EffectSeries.model_validate(
            {**series.model_dump(), "selected_cells": series.selected_cells[:-1]}
        )


def test_v2_declares_its_interrupted_predecessor() -> None:
    series = load_c0045_effect_series(SERIES_V2_PATH)

    assert series.schema_version == "c0045-compute-effect-series/v2"
    assert series.predecessor_status == "interrupted_post_boot_dependency_failure"
    assert series.receipt_root_name == "c0045-series-v2"


def test_v2_rejects_missing_predecessor() -> None:
    values = load_c0045_effect_series(SERIES_V2_PATH).model_dump()
    values["predecessor_series_sha256"] = None

    with pytest.raises(ValueError, match="must declare its interrupted predecessor"):
        C0045EffectSeries(**values)
