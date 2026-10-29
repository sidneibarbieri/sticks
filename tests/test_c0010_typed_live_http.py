"""A live HTTP observation is retained before teardown but granted after completion."""

from pathlib import Path
from uuid import uuid4

import pytest

from executors import legacy_campaign_executors
from executors.executor_registry import registry
from runners import c0010_controller_observers, c0010_http_observer
from runners.c0010_controller_observers import controller_request
from runners.c0010_http_observer import C0010HttpRequest, HttpBodySpec
from runners.c0010_runtime_contracts import load_c0010_runtime_contracts
from runners.campaign_runner import LiveObserverBinding, UnifiedCampaignRunner
from runners.capability_facts import FactScope


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runner = UnifiedCampaignRunner("0.c0010", tmp_path / "output")
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr(
        legacy_campaign_executors, "ARTIFACTS_DIR", root / "data/artifacts"
    )
    monkeypatch.setattr(c0010_controller_observers, "_PROJECT_ROOT", root)
    guest_scope = FactScope(
        run_id=runner.run_id,
        environment_id=f"lab-{runner.run_id}",
        epoch="test-boot",
        locus="target",
        host_id="target-linux-1",
        principal="ubuntu",
    )
    contracts = load_c0010_runtime_contracts(guest_scope, registry)
    run_root = tmp_path / "run"
    run_root.mkdir()
    controller_scope = contracts[2].scope
    staged = runner.execute_contracted_occurrence(
        contracts[2],
        {
            "c0010-page": controller_request(
                "c0010-page", controller_scope, uuid4().hex, 3
            )
        },
        run_root=run_root,
    )
    assert staged.authorizing_facts[0].name == "controller:watering_hole_staged"

    def request_for_port(port):
        return C0010HttpRequest(
            sut_profile_id="0.c0010",
            scope=contracts[3].scope,
            nonce=uuid4().hex,
            producer_occurrence=4,
            port=port,
        )

    return runner, contracts[3], run_root, request_for_port


def test_live_http_observation_grants_only_controller_fact(tmp_path, monkeypatch):
    runner, contract, run_root, request_for_port = _setup(tmp_path, monkeypatch)

    outcome = runner.execute_contracted_occurrence(
        contract,
        {},
        run_root=run_root,
        live_observer=LiveObserverBinding("c0010-http", request_for_port),
    )

    assert outcome.invocation.executor_completed
    assert len(outcome.observation_references) == 1
    assert outcome.observations[0].passed
    assert [fact.name for fact in outcome.authorizing_facts] == [
        "controller:watering_hole_fetched"
    ]
    assert not any(fact.scope.locus == "target" for fact in outcome.authorizing_facts)


def test_failed_live_http_observation_preserves_error_without_fact(
    tmp_path, monkeypatch
):
    runner, contract, run_root, request_for_port = _setup(tmp_path, monkeypatch)
    monkeypatch.setitem(
        c0010_http_observer._EXPECTED_BODIES,
        "/index.html",
        HttpBodySpec(sha256="0" * 64, size=93),
    )

    with pytest.raises(RuntimeError, match="observation did not pass"):
        runner.execute_contracted_occurrence(
            contract,
            {},
            run_root=run_root,
            live_observer=LiveObserverBinding("c0010-http", request_for_port),
        )

    assert not any(
        fact.name == "controller:watering_hole_fetched"
        for fact in runner.fact_store.snapshot()
    )
    assert runner.runtime_journal_references
