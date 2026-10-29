"""Campaigns with a typed contract for live laboratory execution."""

LIVE_CAMPAIGNS = frozenset({"0.c0010", "0.c0026", "0.costaricto", "0.shadowray"})


def require_live_campaign(campaign_id: str) -> None:
    if campaign_id not in LIVE_CAMPAIGNS:
        raise ValueError(
            f"Campaign {campaign_id} has no typed runtime contract for live SUT execution; "
            "legacy local executors cannot establish campaign/SUT effects"
        )
