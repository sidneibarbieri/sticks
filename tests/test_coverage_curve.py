"""The coverage curve must be monotone, deterministic, and end at full coverage."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from evaluation.coverage_curve import greedy_coverage_curve, supported_steps
from scripts.build_coverage_curve_evidence import (
    DEFAULT_PLANS_DIR,
    build_curve,
    load_campaigns,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _figure_coordinates(figure: str) -> list[tuple[int, float]]:
    tikz_curve = re.search(r"\\def\\curve\{([^}]+)\}", figure)
    if tikz_curve is not None:
        return [
            (int(size), float(rate))
            for size, rate in re.findall(r"(\d+)/([\d.]+)", tikz_curve.group(1))
        ]
    plot = re.search(r"plot coordinates \{([^}]+)\}", figure)
    assert plot is not None, "Coverage figure has no recognized data coordinates"
    return [
        (int(size), float(rate))
        for size, rate in re.findall(r"\((\d+),([\d.]+)\)", plot.group(1))
    ]


@pytest.mark.parametrize(
    "figure",
    [r"\def\curve{0/0, 1/2.5}", "plot coordinates {(0,0) (1,2.5)}"],
)
def test_figure_coordinate_formats(figure: str) -> None:
    assert _figure_coordinates(figure) == [(0, 0.0), (1, 2.5)]


def _step(technique_id: str, execution_domain: str = "attacker") -> dict:
    return {"technique_id": technique_id, "execution_domain": execution_domain}


def _template(
    template_id: str, technique_id: str, execution_domain: str = "attacker"
) -> dict:
    return {
        "template_id": template_id,
        "technique_ids": [technique_id],
        "execution_domain": execution_domain,
        "evidence_predicates": [{"name": template_id, "role": "effect"}],
        "fidelity_ceiling": "exact",
    }


def _synthetic_campaigns() -> dict[str, list[dict]]:
    return {
        "A": [_step("T1"), _step("T1"), _step("T1"), _step("T2"), _step("T9")],
        "B": [_step("T2"), _step("T3")],
    }


def _synthetic_templates() -> list[dict]:
    return [
        _template("covers-t1", "T1"),
        _template("covers-t2", "T2"),
        _template("covers-t3", "T3"),
        _template("covers-unused", "T404"),
    ]


def test_endpoint_matches_full_catalog_coverage() -> None:
    campaigns, templates = _synthetic_campaigns(), _synthetic_templates()
    curve = greedy_coverage_curve(campaigns, templates)
    assert curve.points[-1].supported_steps == supported_steps(campaigns, templates)
    assert curve.full_catalog_supported_steps == curve.points[-1].supported_steps


def test_coverage_is_monotone_non_decreasing() -> None:
    curve = greedy_coverage_curve(_synthetic_campaigns(), _synthetic_templates())
    supported = [point.supported_steps for point in curve.points]
    assert supported == sorted(supported)
    assert all(point.marginal_steps >= 0 for point in curve.points)


def test_marginal_steps_sum_to_the_endpoint() -> None:
    curve = greedy_coverage_curve(_synthetic_campaigns(), _synthetic_templates())
    assert (
        sum(point.marginal_steps for point in curve.points)
        == curve.full_catalog_supported_steps
    )


def test_greedy_orders_the_highest_coverage_template_first() -> None:
    # T1 appears in three corpus steps, more than T2 (two) or T3 (one).
    curve = greedy_coverage_curve(_synthetic_campaigns(), _synthetic_templates())
    assert curve.points[0].template_id == "covers-t1"
    assert curve.points[0].marginal_steps == 3


def test_a_template_for_an_absent_technique_adds_nothing() -> None:
    curve = greedy_coverage_curve(_synthetic_campaigns(), _synthetic_templates())
    unused = next(
        point for point in curve.points if point.template_id == "covers-unused"
    )
    assert unused.marginal_steps == 0


def test_ordering_is_deterministic_across_input_permutations() -> None:
    campaigns = _synthetic_campaigns()
    templates = _synthetic_templates()
    forward = greedy_coverage_curve(campaigns, templates)
    reversed_curve = greedy_coverage_curve(campaigns, list(reversed(templates)))
    assert [point.template_id for point in forward.points] == [
        point.template_id for point in reversed_curve.points
    ]


def test_duplicate_template_ids_are_rejected() -> None:
    template = _synthetic_templates()[0]
    with pytest.raises(ValueError, match="unique template IDs"):
        greedy_coverage_curve(_synthetic_campaigns(), [template, template])


def test_empty_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="nonempty template catalog"):
        greedy_coverage_curve(_synthetic_campaigns(), [])
    with pytest.raises(ValueError, match="corpus steps"):
        greedy_coverage_curve({}, _synthetic_templates())


def test_loader_rejects_missing_and_duplicate_campaigns(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No procedural plans"):
        load_campaigns(tmp_path)
    for filename in ("first.procedural-plan.json", "second.procedural-plan.json"):
        (tmp_path / filename).write_text(
            json.dumps({"campaign_id": "duplicate", "steps": []}), encoding="utf-8"
        )
    with pytest.raises(ValueError, match="Duplicate campaign ID"):
        load_campaigns(tmp_path)


def test_matches_frozen_corpus_evidence() -> None:
    record_path = (
        PROJECT_ROOT / "release" / "experiments" / "coverage_curve" / "corpus.json"
    )
    substitution_path = (
        PROJECT_ROOT / "release" / "experiments" / "substitution" / "corpus.json"
    )
    assert record_path.is_file()
    assert substitution_path.is_file()
    curve = json.loads(record_path.read_text(encoding="utf-8"))
    substitution = json.loads(substitution_path.read_text(encoding="utf-8"))
    assert (
        curve["full_catalog_supported_steps"] == substitution["catalog_supported_steps"]
    )
    assert curve["total_steps"] == substitution["total_steps"]
    assert build_curve(DEFAULT_PLANS_DIR).model_dump() == curve


def test_figure_coordinates_match_frozen_curve() -> None:
    record_path = (
        PROJECT_ROOT / "release" / "experiments" / "coverage_curve" / "corpus.json"
    )
    paper_dir = os.environ.get("PAPER_DIR")
    figure_path = (
        (Path(paper_dir) if paper_dir else PROJECT_ROOT.parent / "paper")
        / "figures"
        / "coverage-curve.tex"
    )
    if paper_dir:
        assert figure_path.is_file(), "PAPER_DIR lacks the coverage-curve figure"
    elif not figure_path.is_file():
        pytest.skip("Manuscript not packaged; set PAPER_DIR to verify the figure")
    curve = json.loads(record_path.read_text(encoding="utf-8"))
    figure = figure_path.read_text(encoding="utf-8")
    coordinates = _figure_coordinates(figure)
    expected = [(0, 0.0)] + [
        (point["catalog_size"], round(100 * point["coverage_rate"], 2))
        for point in curve["points"]
    ]
    assert coordinates == expected
