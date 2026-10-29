from __future__ import annotations

import pytest

from scripts.render_c0045_series_macros import render, summarize


def test_summary_reports_counts_ranges_and_threshold_crossings() -> None:
    cells = {
        "b1-treatment": ("treatment", 143), "b2-treatment": ("treatment", 4),
        "b1-busy": ("busy", 140), "b1-idle": ("idle", 0),
        "b1-controller_only": ("controller_only", 0),
    }

    macros = summarize(cells, threshold=5)

    assert macros["Cells"] == 5
    assert macros["Threshold"] == 5
    assert (macros["TreatmentN"], macros["TreatmentMin"], macros["TreatmentMax"]) == (2, 4, 143)
    assert macros["TreatmentAbove"] == 1
    assert macros["BusyAbove"] == 1
    assert macros["IdleAbove"] == 0
    assert macros["ControllerMax"] == 0


def test_summary_rejects_a_missing_arm() -> None:
    with pytest.raises(ValueError, match="no busy cell"):
        summarize({"b1-treatment": ("treatment", 143)}, threshold=5)


def test_render_binds_the_archive_digest() -> None:
    text = render({"Cells": 20}, "a" * 64)

    assert "% C0045 effect-series archive SHA-256: " + "a" * 64 in text
    assert "\\newcommand{\\cxsCells}{20}" in text
