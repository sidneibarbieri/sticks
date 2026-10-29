from __future__ import annotations

from functools import lru_cache
import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "analyze_campaigns.py"
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


def test_generated_macros_match_the_declared_paper1_contract() -> None:
    module, report = _load_report()

    generated_macros = set(report["macro_values"])
    declared_macros = {
        macro_name
        for _, macro_names in module.LATEX_GROUPS
        for macro_name in macro_names
    }

    assert generated_macros == declared_macros
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
