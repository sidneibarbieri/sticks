"""CostaRicto must dispatch to a typed plan and refuse a missing guest."""

import json

import pytest

from runners import campaign_runner
from runners.capability_facts import FactScope
from runners.costaricto_capability_observers import costaricto_effect_request


def test_missing_guest_retains_all_ten_planned_occurrences(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign_runner, "detect_lab_infrastructure", lambda _: "")
    runner = campaign_runner.UnifiedCampaignRunner("0.costaricto", tmp_path)

    with pytest.raises(RuntimeError, match="reachable guest"):
        runner.run()

    run_root = tmp_path / "runtime-v2" / runner.run_id
    plan = json.loads((run_root / "plan.json").read_text())
    summary = json.loads((run_root / "summary.json").read_text())
    assert len(plan["steps"]) == 10
    assert all(step["status"] == "not_run" for step in summary["steps"])
    assert summary["effects_observed"] == 0
    assert summary["error_type"] == "RuntimeError"


def test_observer_requests_bind_occurrences_and_reject_wrong_authority():
    scope = FactScope(
        run_id="run-a",
        environment_id="lab-a",
        epoch="boot-a",
        locus="target",
        host_id="target-linux-1",
        principal="reconuser",
    )
    request = costaricto_effect_request(
        "costaricto-discovery", scope, "fresh-challenge", 1
    )
    assert request.predicate_id == "local-service-listing"
    assert request.producer_occurrence == 1
    with pytest.raises(ValueError, match="Unknown CostaRicto"):
        costaricto_effect_request("c0026-collection", scope, "fresh-challenge", 1)
    with pytest.raises(ValueError, match="producing occurrence"):
        costaricto_effect_request("costaricto-collection", scope, "fresh-challenge", 2)
