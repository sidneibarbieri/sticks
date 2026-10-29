from pathlib import Path

from runners import campaign_runner


def test_declared_sut_weakness_does_not_grant_runtime_authority(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(campaign_runner, "bootstrap_campaign_executors", lambda _: None)

    runner = campaign_runner.UnifiedCampaignRunner("0.c0010", tmp_path)

    assert any(
        weakness.weakness_type in {"weak_credentials", "weak_ssh_password"}
        for host in runner.sut.hosts.values()
        for weakness in host.deliberate_weaknesses
    )
    assert "access:initial" not in runner.accumulated_capabilities
    assert "code_execution" not in runner.accumulated_capabilities
