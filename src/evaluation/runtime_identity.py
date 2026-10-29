"""Reviewed plan-to-runtime identities for the controlled-comparison slice."""

from types import MappingProxyType


REVIEWED_RUNTIME_CAMPAIGNS = MappingProxyType({
    "C0010": "0.c0010",
    "C0026": "0.c0026",
    "C0045": "0.shadowray",
})


def expected_runtime_campaign(campaign_id: str) -> str:
    """Reject undeclared identities rather than guessing a legacy runtime alias."""
    if campaign_id not in REVIEWED_RUNTIME_CAMPAIGNS:
        raise ValueError("No reviewed runtime identity for selected campaign")
    return REVIEWED_RUNTIME_CAMPAIGNS[campaign_id]
