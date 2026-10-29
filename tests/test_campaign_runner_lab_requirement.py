from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNNER_PATH = PROJECT_ROOT / "src" / "runners" / "campaign_runner.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("campaign_runner_lab", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_legacy_campaign_is_rejected_without_a_lab(monkeypatch, tmp_path) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "detect_lab_infrastructure", lambda _: "")
    runner = module.UnifiedCampaignRunner(
        "0.c0011", tmp_path, require_lab=True
    )

    with pytest.raises(ValueError, match="typed runtime contract"):
        runner.run()


def test_reachable_lab_does_not_authorize_legacy_local_executors(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "detect_lab_infrastructure", lambda _: "qemu")
    runner = module.UnifiedCampaignRunner("0.c0011", tmp_path, require_lab=True)
    monkeypatch.setattr(runner, "_execute_step", lambda *args: pytest.fail("Legacy executor must not run"))
    with pytest.raises(ValueError, match="typed runtime contract"):
        runner.run()
    assert not list(tmp_path.rglob("summary.json"))
