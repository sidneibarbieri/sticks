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


def test_results_directory_allows_only_values_tex(tmp_path: Path) -> None:
    module = _load_module(HYGIENE_SCRIPT, "check_paper_hygiene")
    paper_dir = tmp_path / "paper"
    results_dir = paper_dir / "results"
    results_dir.mkdir(parents=True)
    (results_dir / "values.tex").write_text("% ok", encoding="utf-8")
    (results_dir / "extra.json").write_text("{}", encoding="utf-8")

    extras = module.check_results_directory(paper_dir)

    assert extras == ["results/extra.json"]


def test_root_residue_detection_flags_main_aux(tmp_path: Path) -> None:
    module = _load_module(HYGIENE_SCRIPT, "check_paper_hygiene_residue")
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "main.aux").write_text("", encoding="utf-8")

    residue = module.check_root_residue(paper_dir)

    assert residue == ["main.aux"]


def test_clean_root_residue_removes_known_files(tmp_path: Path) -> None:
    module = _load_module(BUILD_SCRIPT, "build_manuscript")
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    for name in ("main.aux", "main.log", "main.out"):
        (paper_dir / name).write_text("stale", encoding="utf-8")

    module.clean_root_residue(paper_dir)

    assert not any((paper_dir / name).exists() for name in ("main.aux", "main.log", "main.out"))
