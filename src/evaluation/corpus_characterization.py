"""Characterize what the public corpus itself documents, independent of any catalog.

Catalog coverage measures our template catalog; it says nothing about the intelligence. This
module measures the corpus directly: how much of the technique space campaigns reference, how
much intrusion sets reference, and how those two populations differ.

The asymmetry is the point. Campaigns document individual operations and reference a narrow
slice; intrusion sets aggregate across operations and reach much wider. Broader technique
reach is behavioral accumulation, not procedural completeness -- neither population encodes the
ordering, parameters, or environment an execution needs. Reported for the pinned bundle only.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

MITRE_SOURCE = "mitre-attack"
CAMPAIGN = "campaign"
INTRUSION_SET = "intrusion-set"
ATTACK_PATTERN = "attack-pattern"
USES = "uses"


class CorpusCharacterization(BaseModel):
    """Technique reach of each documenting population in one pinned bundle."""

    model_config = ConfigDict(extra="forbid")

    question: str
    active_techniques: int
    campaign_referenced: int
    intrusion_set_referenced: int
    campaign_reference_rate: float
    intrusion_set_reference_rate: float
    campaign_only: int
    referenced_by_both: int
    intrusion_set_only: int
    referenced_by_neither: int
    note: str


def _is_active(item: dict) -> bool:
    return not item.get("revoked") and not item.get("x_mitre_deprecated")


def _attack_identifier(item: dict) -> str | None:
    for reference in item.get("external_references", []):
        if reference.get("source_name") == MITRE_SOURCE:
            return reference.get("external_id")
    return None


def technique_identifiers(objects: list[dict]) -> dict[str, str]:
    """STIX identifier to ATT&CK identifier for every active technique."""
    identifiers = {}
    for item in objects:
        if item.get("type") == ATTACK_PATTERN and _is_active(item):
            external_id = _attack_identifier(item)
            if external_id is not None:
                identifiers[item["id"]] = external_id
    return identifiers


def techniques_referenced_by(
    objects: list[dict], source_type: str, techniques: dict[str, str]
) -> set[str]:
    """Techniques an active population reaches through `uses` relationships."""
    source_types = {
        item["id"]: item.get("type") for item in objects if _is_active(item)
    }
    return {
        techniques[item["target_ref"]]
        for item in objects
        if item.get("type") == "relationship"
        and item.get("relationship_type") == USES
        and _is_active(item)
        and item.get("target_ref") in techniques
        and source_types.get(item.get("source_ref")) == source_type
    }


def characterize(bundle: dict) -> CorpusCharacterization:
    """Measure how far each documenting population reaches into the technique space."""
    objects = bundle["objects"]
    techniques = technique_identifiers(objects)
    universe = set(techniques.values())
    if not universe:
        raise ValueError("the pinned bundle declares no active techniques")

    campaign = techniques_referenced_by(objects, CAMPAIGN, techniques)
    intrusion_set = techniques_referenced_by(objects, INTRUSION_SET, techniques)

    return CorpusCharacterization(
        question=(
            "How much of the technique space does each documenting population reference?"
        ),
        active_techniques=len(universe),
        campaign_referenced=len(campaign),
        intrusion_set_referenced=len(intrusion_set),
        campaign_reference_rate=len(campaign) / len(universe),
        intrusion_set_reference_rate=len(intrusion_set) / len(universe),
        campaign_only=len(campaign - intrusion_set),
        referenced_by_both=len(campaign & intrusion_set),
        intrusion_set_only=len(intrusion_set - campaign),
        referenced_by_neither=len(universe - campaign - intrusion_set),
        note=(
            "Reference rates measure documented behavioral reach, not procedural "
            "completeness: neither population encodes the ordering, parameters, or "
            "environment binding an execution requires."
        ),
    )
