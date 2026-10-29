"""Compile ATT&CK campaign relationships into a deterministic procedural IR."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from contracts.procedural_ir import ProcedureStep, ProceduralPlan, SourceSnapshot


def tactic_rank(objects: list[dict[str, Any]]) -> dict[str, int]:
    """Kill-chain rank for each tactic, as the pinned bundle's matrix declares it.

    A hardcoded rank table survives a bundle re-pin unchanged. When ATT&CK v19 replaced
    Defense Evasion with Stealth and Defense Impairment, both new tactics fell outside such
    a table and sorted after Impact, which contradicts the ordering policy this compiler
    declares.
    """
    tactics_by_id = {
        item["id"]: item for item in objects if item.get("type") == "x-mitre-tactic"
    }
    matrices = [item for item in objects if item.get("type") == "x-mitre-matrix"]
    if len(matrices) != 1:
        raise ValueError(
            f"expected one Enterprise matrix in the bundle, found {len(matrices)}"
        )
    return {
        tactics_by_id[reference]["x_mitre_shortname"]: rank
        for rank, reference in enumerate(matrices[0]["tactic_refs"])
    }


def _external_id(stix_object: dict[str, Any]) -> str:
    for reference in stix_object.get("external_references", []):
        if reference.get("source_name") == "mitre-attack":
            return str(reference.get("external_id", ""))
    return ""


def _active(stix_object: dict[str, Any]) -> bool:
    return not stix_object.get("revoked", False) and not stix_object.get(
        "x_mitre_deprecated", False
    )


def _tactics(technique: dict[str, Any], ranks: dict[str, int]) -> list[str]:
    return sorted(
        {
            str(phase["phase_name"])
            for phase in technique.get("kill_chain_phases", [])
            if phase.get("kill_chain_name") == "mitre-attack" and phase.get("phase_name")
        },
        key=lambda tactic: (ranks.get(tactic, len(ranks)), tactic),
    )


def _step_order(step: ProcedureStep, ranks: dict[str, int]) -> tuple[int, str]:
    first_rank = min(
        (ranks.get(tactic, len(ranks)) for tactic in step.tactics),
        default=len(ranks),
    )
    return first_rank, step.technique_id


def _execution_domain(tactics: list[str]) -> str:
    tactic_set = set(tactics)
    if tactic_set and tactic_set <= {"reconnaissance", "resource-development"}:
        return "attacker"
    if tactic_set & {"initial-access", "command-and-control", "exfiltration"}:
        return "boundary"
    return "target"


def compile_campaign(bundle_path: Path, campaign_external_id: str) -> ProceduralPlan:
    bundle_bytes = bundle_path.read_bytes()
    bundle = json.loads(bundle_bytes)
    objects = [item for item in bundle.get("objects", []) if _active(item)]
    by_stix_id = {item["id"]: item for item in objects if item.get("id")}
    ranks = tactic_rank(objects)

    campaigns = [
        item
        for item in objects
        if item.get("type") == "campaign" and _external_id(item) == campaign_external_id
    ]
    if len(campaigns) != 1:
        raise ValueError(
            f"expected one active ATT&CK campaign {campaign_external_id}, found {len(campaigns)}"
        )
    campaign = campaigns[0]

    relationships_by_target: dict[str, list[dict[str, Any]]] = {}
    for relationship in objects:
        if (
            relationship.get("type") == "relationship"
            and relationship.get("relationship_type") == "uses"
            and relationship.get("source_ref") == campaign["id"]
        ):
            relationships_by_target.setdefault(relationship["target_ref"], []).append(
                relationship
            )

    steps: list[ProcedureStep] = []
    for target_ref, relationships in relationships_by_target.items():
        technique = by_stix_id.get(target_ref)
        if technique is None or technique.get("type") != "attack-pattern":
            continue
        technique_id = _external_id(technique)
        if not technique_id.startswith("T"):
            continue
        ordered_relationships = sorted(relationships, key=lambda item: item["id"])
        tactics = _tactics(technique, ranks)
        steps.append(
            ProcedureStep(
                technique_id=technique_id,
                technique_stix_id=technique["id"],
                name=str(technique.get("name", technique_id)),
                execution_domain=_execution_domain(tactics),
                tactics=tactics,
                platforms=sorted(set(technique.get("x_mitre_platforms", []))),
                permissions_required=sorted(
                    set(technique.get("x_mitre_permissions_required", []))
                ),
                system_requirements=sorted(
                    set(technique.get("x_mitre_system_requirements", []))
                ),
                relationship_ids=[item["id"] for item in ordered_relationships],
                procedure_descriptions=[
                    str(item["description"])
                    for item in ordered_relationships
                    if item.get("description")
                ],
            )
        )

    if not steps:
        raise ValueError(f"campaign {campaign_external_id} has no active technique uses-links")

    plan = ProceduralPlan(
        campaign_id=campaign_external_id,
        campaign_name=str(campaign.get("name", campaign_external_id)),
        source=SourceSnapshot(
            bundle_sha256=hashlib.sha256(bundle_bytes).hexdigest(),
            object_count=len(bundle.get("objects", [])),
            campaign_stix_id=campaign["id"],
            campaign_external_id=campaign_external_id,
        ),
        steps=sorted(steps, key=lambda step: _step_order(step, ranks)),
        limitations=[
            "ATT&CK uses-links do not encode a historical total order; the compiler applies a declared tactic-rank policy.",
            "Technique metadata constrains procedures but does not uniquely determine an executable target environment.",
        ],
    )
    plan.finalize_hash()
    return plan
