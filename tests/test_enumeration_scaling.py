from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.solver import enumerate_candidates


def _load_script():
    path = PROJECT_ROOT / "scripts" / "build_enumeration_scaling_evidence.py"
    spec = importlib.util.spec_from_file_location("enumeration_scaling", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


@pytest.mark.parametrize(
    ("templates", "parameters", "bindings"),
    [(1, 1, 1), (1, 2, 3), (4, 2, 5), (3, 3, 4)],
)
def test_closed_form_predicts_the_enumerated_count(templates, parameters, bindings):
    point = SCRIPT.measure(templates, parameters, bindings)
    assert point.predicted_candidates == point.enumerated_candidates


def test_a_kind_no_template_consumes_does_not_enlarge_the_domain():
    step = SCRIPT.build_step()
    templates = SCRIPT.build_templates(1, 1)
    lean = SCRIPT.build_catalog(1, 4)
    padded = SCRIPT.build_catalog(3, 4)

    assert len(enumerate_candidates(step, templates, lean)) == 4
    assert len(enumerate_candidates(step, templates, padded)) == 4


def test_a_domain_above_the_ceiling_is_refused_not_truncated():
    step = SCRIPT.build_step()
    templates = SCRIPT.build_templates(4, 2)
    catalog = SCRIPT.build_catalog(2, 8)

    with pytest.raises(ValueError, match="rather than reporting a truncated candidate set"):
        enumerate_candidates(step, templates, catalog, maximum_candidates=8)


def test_the_released_grid_records_agreement_everywhere():
    payload = json.loads(
        (PROJECT_ROOT / "release/experiments/enumeration_scaling/corpus.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["closed_form_agrees_everywhere"] is True
    assert payload["refusal_probe"]["refused"] is True
    for point in payload["points"]:
        assert point["predicted_candidates"] == point["enumerated_candidates"]
