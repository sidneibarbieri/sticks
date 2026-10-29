#!/usr/bin/env python3
"""
Campaign executor bootstrap - ensures deterministic executor registration.
"""


def bootstrap_campaign_executors(campaign_id: str):
    """
    Bootstrap executors for a specific campaign.

    Args:
        campaign_id: ID of the campaign (e.g., '0.mustang_panda', '0.fox_kitten')
    """
    # Base executors for all campaigns

    # Fox Kitten specific executors
    if campaign_id == "0.fox_kitten":
        pass

    # ShadowRay specific executors
    elif campaign_id == "0.shadowray":
        pass

    return True


def get_campaign_executor_count(campaign_id: str) -> dict:
    """
    Get executor statistics for a campaign.

    Returns:
        Dict with total, registered, and missing executors
    """
    from executors.executor_registry import registry
    from loaders.campaign_loader import load_campaign

    campaign = load_campaign(campaign_id)
    technique_ids = [step.technique_id for step in campaign.steps]

    missing_techniques = [
        technique_id
        for technique_id in technique_ids
        if registry.get_executor(technique_id, campaign_id) is None
    ]
    missing = len(missing_techniques)
    registered = len(technique_ids) - missing

    return {
        "campaign_id": campaign_id,
        "total_techniques": len(technique_ids),
        "registered_executors": registered,
        "missing_executors": missing,
        "registration_rate": registered / len(technique_ids) if technique_ids else 0,
        "missing_techniques": missing_techniques,
    }


if __name__ == "__main__":
    # Test bootstrap for all campaigns
    for campaign in ["0.mustang_panda", "0.fox_kitten", "0.shadowray"]:
        print(f"\n=== BOOTSTRAP FOR {campaign} ===")
        bootstrap_campaign_executors(campaign)
        stats = get_campaign_executor_count(campaign)
        print(f"Total: {stats['total_techniques']}")
        print(f"Registered: {stats['registered_executors']}")
        print(f"Missing: {stats['missing_executors']}")
        print(f"Rate: {stats['registration_rate']:.1%}")
        if stats["missing_techniques"]:
            print(f"Missing: {', '.join(stats['missing_techniques'])}")
