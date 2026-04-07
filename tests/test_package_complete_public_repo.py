from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / "scripts" / "package_complete_public_repo.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("sticks_package_complete_public_repo", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_measurement_sut_internal_docs_are_excluded_from_public_package() -> None:
    module = _load_module()
    ignore = module.ignore_for_directory("measurement")
    sut_dir = module.STICKS_ROOT / "measurement" / "sut"
    names = [
        "FINAL_STATUS.md",
        "PUBLICATION_CHECKLIST.md",
        "README.md",
        "TRACEABILITY.md",
    ]

    ignored = ignore(str(sut_dir), names)

    assert "FINAL_STATUS.md" in ignored
    assert "PUBLICATION_CHECKLIST.md" in ignored
    assert "README.md" not in ignored
    assert "TRACEABILITY.md" not in ignored


def test_internal_docs_root_files_are_excluded_from_public_package() -> None:
    module = _load_module()
    ignore = module.ignore_for_directory("docs")
    docs_dir = module.STICKS_ROOT / "docs"
    names = [
        "ARCHITECTURE_FREEZE.md",
        "LEGACY_REMOVAL_RECORD.md",
        "artifact_evaluation.md",
        "reviewer_quickstart.md",
    ]

    ignored = ignore(str(docs_dir), names)

    assert "ARCHITECTURE_FREEZE.md" in ignored
    assert "LEGACY_REMOVAL_RECORD.md" in ignored
    assert "artifact_evaluation.md" not in ignored
    assert "reviewer_quickstart.md" not in ignored
