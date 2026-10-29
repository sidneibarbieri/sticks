from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
HYGIENE_SCRIPT = PROJECT_ROOT / "scripts" / "check_paper_hygiene.py"
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_manuscript.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _paper(tmp_path: Path, manuscript: str) -> Path:
    paper_dir = tmp_path / "paper"
    (paper_dir / "results").mkdir(parents=True)
    (paper_dir / "figures").mkdir(parents=True)
    (paper_dir / "main.tex").write_text(manuscript, encoding="utf-8")
    return paper_dir


def test_a_generated_file_the_manuscript_stopped_loading_is_reported(tmp_path: Path) -> None:
    module = _load_module(HYGIENE_SCRIPT, "check_paper_hygiene")
    paper_dir = _paper(tmp_path, "\\input{results/macros.tex}")
    (paper_dir / "results" / "macros.tex").write_text("% loaded", encoding="utf-8")
    (paper_dir / "results" / "stale.tex").write_text("% orphaned", encoding="utf-8")

    assert module.find_unreachable_sources(paper_dir) == ["results/stale.tex"]


def test_a_style_file_reached_through_a_figure_is_not_reported(tmp_path: Path) -> None:
    module = _load_module(HYGIENE_SCRIPT, "check_paper_hygiene_reach")
    paper_dir = _paper(tmp_path, "\\input{figures/diagram.tex}")
    (paper_dir / "figures" / "diagram.tex").write_text(
        "\\input{figures/housestyle.tex}", encoding="utf-8"
    )
    (paper_dir / "figures" / "housestyle.tex").write_text("% shared scale", encoding="utf-8")

    assert module.find_unreachable_sources(paper_dir) == []


def test_root_residue_detection_flags_main_aux(tmp_path: Path) -> None:
    module = _load_module(HYGIENE_SCRIPT, "check_paper_hygiene_residue")
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "main.aux").write_text("", encoding="utf-8")

    assert module.find_build_residue(paper_dir) == ["main.aux"]


def test_a_superseded_document_class_is_reported(tmp_path: Path) -> None:
    module = _load_module(HYGIENE_SCRIPT, "check_paper_hygiene_class")
    paper_dir = _paper(tmp_path, "\\documentclass[conference]{IEEEtran}\n\\bibliographystyle{IEEEtran}")
    (paper_dir / "IEEEtran.cls").write_text("% current", encoding="utf-8")
    (paper_dir / "IEEEtran.bst").write_text("% current", encoding="utf-8")
    (paper_dir / "acmart.cls").write_text("% superseded", encoding="utf-8")
    (paper_dir / "main.tex.acmart-backup").write_text("% superseded", encoding="utf-8")

    assert module.find_superseded_typesetting(paper_dir) == [
        "acmart.cls",
        "main.tex.acmart-backup",
    ]


def test_clean_root_residue_removes_known_files(tmp_path: Path) -> None:
    module = _load_module(BUILD_SCRIPT, "build_manuscript")
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    for name in ("main.aux", "main.log", "main.out"):
        (paper_dir / name).write_text("stale", encoding="utf-8")

    module.clean_root_residue(paper_dir)

    assert not any((paper_dir / name).exists() for name in ("main.aux", "main.log", "main.out"))
