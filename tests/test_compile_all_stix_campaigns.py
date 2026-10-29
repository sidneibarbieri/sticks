from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compile_all_stix_campaigns.py"


def _module():
    spec = importlib.util.spec_from_file_location("compile_all_stix_campaigns", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_active_campaign_ids_are_sorted_and_unique() -> None:
    module = _module()
    bundle = Path(__file__).resolve().parents[1] / "data" / "stix" / "enterprise-attack.json"
    campaign_ids = module.active_campaign_ids(bundle)
    assert campaign_ids == sorted(set(campaign_ids))
    assert "C0045" in campaign_ids
