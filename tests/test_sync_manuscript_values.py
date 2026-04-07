from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "sync_manuscript_values.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("sync_manuscript_values", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_write_report_includes_both_papers_when_results_are_mixed(tmp_path: Path) -> None:
    module = _load_module()
    original_json = module.OUTPUT_JSON
    original_md = module.OUTPUT_MD
    module.OUTPUT_JSON = tmp_path / "manuscript_values_sync.json"
    module.OUTPUT_MD = tmp_path / "MANUSCRIPT_VALUES_SYNC.md"

    try:
        module.write_report(
            [
                module.SyncResult(
                    paper="paper1",
                    status="checked",
                    details="Paper 1 current values.tex checked.",
                    macros_written=40,
                ),
                module.SyncResult(
                    paper="paper2",
                    status="updated",
                    details="Paper 2 values.tex replaced.",
                    macros_written=133,
                ),
            ]
        )
    finally:
        module.OUTPUT_JSON = original_json
        module.OUTPUT_MD = original_md

    report_text = (tmp_path / "MANUSCRIPT_VALUES_SYNC.md").read_text(encoding="utf-8")
    assert "## paper1" in report_text
    assert "## paper2" in report_text
    assert "- Status: `checked`" in report_text
    assert "- Status: `updated`" in report_text
