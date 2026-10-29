"""C0010 must not silently return legacy campaign evidence without a guest."""

import json

import pytest

from runners import campaign_runner
from runners.capability_facts import ObservationReference
from runners.lab_runtime_bootstrap import LabBootstrapOutcome


def test_c0010_run_refuses_missing_guest_and_retains_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign_runner, "detect_lab_infrastructure", lambda _: "")
    runner = campaign_runner.UnifiedCampaignRunner("0.c0010", tmp_path)

    with pytest.raises(RuntimeError, match="reachable guest"):
        runner.run()

    run_root = tmp_path / "runtime-v2" / runner.run_id
    plan = json.loads((run_root / "plan.json").read_text())
    summary = json.loads((run_root / "summary.json").read_text())
    assert len(plan["steps"]) == 9
    assert all(step["status"] == "not_run" for step in summary["steps"])
    assert summary["error_type"] == "RuntimeError"
    assert summary["effects_observed"] == 0


def test_c0010_missing_profile_blocks_every_action(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign_runner, 'detect_lab_infrastructure', lambda _: 'qemu')
    runner = campaign_runner.UnifiedCampaignRunner('0.c0010', tmp_path)
    measured_scope = campaign_runner.FactScope(
        run_id=runner.run_id, environment_id=f'lab-{runner.run_id}', epoch='test-boot',
        locus='target', host_id='target-linux-1', principal='ubuntu')
    reference = ObservationReference(authority_id='lab-shell', predicate_id='shell-nonce',
        record_path='observations/test.json', record_sha256='a' * 64)
    bootstrap = LabBootstrapOutcome(scope=measured_scope, discovery_reference=reference,
                                    reference=reference, facts=())
    monkeypatch.setattr(campaign_runner, 'bootstrap_lab_authority', lambda **kwargs: bootstrap)
    def refuse_profile(*args):
        raise ValueError('profile fixture missing')
    monkeypatch.setattr(campaign_runner, 'require_c0010_fixture_readiness', refuse_profile, raising=False)
    calls = []
    def unexpected_action(*args, **kwargs):
        calls.append('action')
        raise RuntimeError('An action ran before fixture readiness')
    monkeypatch.setattr(runner, 'execute_contracted_occurrence', unexpected_action)
    monkeypatch.setattr(runner, '_refresh_guest_authority', lambda *args: None)
    with pytest.raises(ValueError, match='profile fixture missing'):
        runner.run()
    assert calls == []
    summary = json.loads((tmp_path/'runtime-v2'/runner.run_id/'summary.json').read_text())
    assert all(step['status'] == 'not_run' for step in summary['steps'])
    assert summary['error_type'] == 'ValueError'
