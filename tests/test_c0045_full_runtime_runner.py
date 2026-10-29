"""Full C0045 runner wiring retains observer scope and live trace binding."""

import hashlib

import pytest

from executors.c0045_trace_executor import C0045TraceSelection
from executors.c0045_readonly_commands import command_spec
from executors.campaign_bootstrap import bootstrap_campaign_executors
from executors.executor_registry import registry
from executors.registry_initializer import initialize_registry
from runners.c0045_api_observer import C0045ApiRequest
from runners.c0045_fixture_observer import C0045FixtureRequest
from runners.c0045_full_runtime_contracts import load_c0045_full_runtime_contracts
from runners.c0045_trace_observer import C0045TraceRequest
from runners.campaign_runner import UnifiedCampaignRunner
from runners.capability_facts import FactScope
from runners.runtime_invocation import RuntimeReadinessError


def contracts():
    initialize_registry()
    bootstrap_campaign_executors("0.shadowray")
    scope = FactScope(
        run_id="run-c0045",
        environment_id="lab-c0045",
        epoch="boot-c0045",
        locus="target",
        host_id="target-linux-1",
        principal="rayuser",
    )
    return load_c0045_full_runtime_contracts(scope, registry)


def test_full_runner_constructs_only_declared_c0045_observers(tmp_path):
    runner = UnifiedCampaignRunner("0.shadowray", tmp_path)
    by_occurrence = {contract.occurrence: contract for contract in contracts()}

    api = runner._c0045_observer_requests(by_occurrence[1])["c0045-api"]
    toolkit = runner._c0045_observer_requests(by_occurrence[5])["c0045-toolkit"]
    transfer = runner._c0045_observer_requests(by_occurrence[6])["c0045-transfer"]

    assert isinstance(api, C0045ApiRequest) and api.producer_occurrence == 1
    assert isinstance(toolkit, C0045FixtureRequest)
    assert toolkit.predicate_id == "toolkit-staged" and toolkit.producer_occurrence == 5
    assert isinstance(transfer, C0045FixtureRequest)
    assert (
        transfer.predicate_id == "loopback-transfer"
        and transfer.producer_occurrence == 6
    )
    assert runner._c0045_observer_requests(by_occurrence[2]) == {}


def test_full_runner_binds_live_trace_kind_to_matching_occurrence(tmp_path):
    runner = UnifiedCampaignRunner("0.shadowray", tmp_path)
    by_occurrence = {contract.occurrence: contract for contract in contracts()}

    binding = runner._c0045_live_observer(by_occurrence[7])
    assert binding is not None and binding.authority_id == "c0045-python"
    request = binding.request_for_trace(
        C0045TraceSelection(
            kind="python",
            nonce="a" * 32,
            command_sha256=hashlib.sha256(
                command_spec("python").script.encode()
            ).hexdigest(),
        )
    )
    assert isinstance(request, C0045TraceRequest)
    assert request.producer_occurrence == 7 and request.scope == by_occurrence[7].scope
    assert runner._c0045_live_observer(by_occurrence[8]).authority_id == "c0045-network"
    assert runner._c0045_live_observer(by_occurrence[5]) is None


def test_full_runner_applies_and_retains_declared_sut_delta(tmp_path, monkeypatch):
    runner = UnifiedCampaignRunner("0.shadowray", tmp_path)
    runner._infrastructure_provider = "qemu"
    first = contracts()[0]
    received = {}

    def apply_delta(**kwargs):
        received.update(kwargs)
        return {"applied": ["ray-dashboard"], "errors": [], "notes": "ready"}

    monkeypatch.setattr("runners.campaign_runner.apply_step_sut_delta", apply_delta)
    run_root = tmp_path / "run"
    run_root.mkdir()
    runner._apply_c0045_step_delta(first, run_root)

    assert received["campaign_id"] == "0.shadowray"
    assert "ray-dashboard" in (run_root / "sut_deltas" / "001.json").read_text()


def test_full_runner_refuses_a_failed_declared_sut_delta(tmp_path, monkeypatch):
    runner = UnifiedCampaignRunner("0.shadowray", tmp_path)
    runner._infrastructure_provider = "qemu"
    monkeypatch.setattr(
        "runners.campaign_runner.apply_step_sut_delta",
        lambda **_kwargs: {
            "applied": [],
            "errors": ["service unavailable"],
            "notes": "",
        },
    )
    run_root = tmp_path / "run"
    run_root.mkdir()

    with pytest.raises(RuntimeReadinessError, match="delta application failed"):
        runner._apply_c0045_step_delta(contracts()[0], run_root)
