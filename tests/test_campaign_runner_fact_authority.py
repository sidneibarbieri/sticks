"""Construction retains profile intent without granting runtime authority."""

import pytest

from runners.campaign_runner import UnifiedCampaignRunner

CAMPAIGNS = (
    "0.apt41_dust",
    "0.c0010",
    "0.c0026",
    "0.costaricto",
    "0.operation_midnighteclipse",
    "0.outer_space",
    "0.salesforce_data_exfiltration",
    "0.shadowray",
)


@pytest.mark.parametrize("campaign_id", CAMPAIGNS)
def test_real_constructor_does_not_grant_profile_access(campaign_id, tmp_path):
    runner = UnifiedCampaignRunner(campaign_id, tmp_path, require_lab=True)
    assert "access:initial" not in runner.accumulated_capabilities
    assert "code_execution" not in runner.accumulated_capabilities
    assert not any(fact.origin == "observed" for fact in runner.fact_store.snapshot())


def test_profile_shell_declarations_remain_scoped_and_nonobserved(tmp_path):
    runner = UnifiedCampaignRunner("0.c0026", tmp_path, require_lab=True)
    declarations = runner.fact_store.snapshot()
    assert declarations
    shell = [fact for fact in declarations if fact.name == "lab:shell"]
    assert len(shell) == 1
    assert shell[0].origin == "profile_declaration"
    assert shell[0].scope.host_id == "target-base"
    assert shell[0].scope.principal == "ubuntu"
    assert shell[0].observation is None
