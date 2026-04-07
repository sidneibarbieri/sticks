from __future__ import annotations

from functools import lru_cache
import importlib.util
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "analyze_campaigns.py"
PAPER1_MAIN = PROJECT_ROOT.parent / "ACM CCS - Paper 1" / "main.tex"
PAPER1_VALUES = PROJECT_ROOT.parent / "ACM CCS - Paper 1" / "results" / "values.tex"


@lru_cache(maxsize=1)
def _load_module():
    spec = importlib.util.spec_from_file_location("paper1_analyze_campaigns", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _load_report():
    module = _load_module()
    return module, module.compute_paper1_values(module.DEFAULT_BUNDLE)


def test_generated_macros_cover_every_macro_used_in_paper1_main() -> None:
    _, report = _load_report()

    generated_macros = set(report["macro_values"])
    defined_macros = set(
        re.findall(
            r"\\newcommand\{\\([A-Za-z][A-Za-z0-9]+)\}",
            PAPER1_VALUES.read_text(encoding="utf-8"),
        )
    )
    used_macros = set(re.findall(r"\\([A-Za-z][A-Za-z0-9]+)", PAPER1_MAIN.read_text(encoding="utf-8"))) & defined_macros
    missing = sorted(used_macros - generated_macros)

    assert not missing, f"Paper 1 macros missing from generator output: {missing}"
    assert len(generated_macros) == 40


def test_platform_agnostic_classifier_matches_reported_macro_and_excludes_host_platforms() -> None:
    module, report = _load_report()

    classifier = report["provenance"]["platform_agnostic_classifier"]
    listed = classifier["techniques"]
    assert int(report["macro_values"]["nPlatformAgnosticTechniques"]) == len(listed)

    for item in listed:
        assert not (set(item["platforms"]) & module.CONCRETE_HOST_PLATFORMS)


def test_case_study_provenance_is_explicit_for_shadowray_and_soft_cell() -> None:
    _, report = _load_report()

    case_studies = {item["display_name"]: item for item in report["provenance"]["case_studies"]}

    assert set(case_studies) == {"ShadowRay", "Soft Cell"}
    assert case_studies["ShadowRay"]["local_campaign_id"] == "0.shadowray"
    assert case_studies["Soft Cell"]["stix_name"] == "GALLIUM"
    assert case_studies["Soft Cell"]["description_mentions_display_name"] is True
