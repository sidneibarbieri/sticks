"""The admission comparison must not present verifier agreement as execution."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def test_comparison_table_names_its_actual_outcome() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "render_admission_comparison_table.py"
    spec = importlib.util.spec_from_file_location("render_admission_comparison_table", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    first = module.load_analysis("2026-09-07-local")
    second = module.load_analysis("2026-09-07-qwen14b")
    table = module.render_table(first, second)

    assert "Admitted / emitted" in table
    assert "Validity" not in table
    assert r"Admitted / emitted (\%)" in table
    assert "Raw & no & 83.2 & 79.2 & 0.0 & 0.0" in table
    assert "Procedural & yes & 100.0 & 100.0 & 18.4 & 27.2" in table

    macros = module.render_macros(first, second)
    assert r"\newcommand{\admissionGapFirst}{17.0}" in macros
    assert r"\newcommand{\admissionGapFirstLow}{4.0}" in macros
    assert r"\newcommand{\admittedAbstentionFirst}{18.4}" in macros
