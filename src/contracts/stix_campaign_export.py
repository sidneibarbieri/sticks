"""Export a compact STIX bundle with verified procedural custom properties."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from concretization.models import ActionTemplate, ConcretizedPlan
from contracts.procedural_ir import ProceduralPlan
from contracts.stix_procedure_extension import (
    PROCEDURE_PROPERTY,
    FieldProvenance,
    ProcedureSemantics,
    ValueOrigin,
)


def _load_bundle(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "bundle":
        raise ValueError("source must be a STIX bundle")
    return payload


def _template_index(templates: list[ActionTemplate]) -> dict[str, ActionTemplate]:
    index = {template.template_id: template for template in templates}
    if len(index) != len(templates):
        raise ValueError("action-template identifiers must be unique")
    return index


def export_campaign_bundle(
    *,
    source_bundle_path: Path,
    plan: ProceduralPlan,
    concretized_plan: ConcretizedPlan,
    templates: list[ActionTemplate],
) -> dict[str, Any]:
    if not plan.validate_hash():
        raise ValueError("procedural plan hash mismatch")
    if concretized_plan.source_plan_sha256 != plan.content_sha256:
        raise ValueError("concretized plan does not derive from the procedural plan")
    if concretized_plan.unresolved_technique_ids:
        raise ValueError(
            "cannot export an incomplete procedure extension: "
            + ", ".join(concretized_plan.unresolved_technique_ids)
        )
    if concretized_plan.planning_certificate is None:
        raise ValueError("concretized plan has no planning certificate")
    if not concretized_plan.planning_certificate.valid:
        raise ValueError("concretized plan certificate is invalid")

    bundle = _load_bundle(source_bundle_path)
    source_hash = hashlib.sha256(source_bundle_path.read_bytes()).hexdigest()
    if source_hash != plan.source.bundle_sha256:
        raise ValueError("source bundle differs from the procedural-plan snapshot")
    objects = {
        item["id"]: item
        for item in bundle.get("objects", [])
        if isinstance(item, dict) and item.get("id")
    }
    campaign = objects.get(plan.source.campaign_stix_id)
    if campaign is None:
        raise ValueError("campaign object is absent from the source bundle")

    plan_steps = {step.technique_id: step for step in plan.steps}
    template_by_id = _template_index(templates)
    output_objects: list[dict[str, Any]] = [copy.deepcopy(campaign)]
    included_techniques: set[str] = set()
    included_relationships: set[str] = set()

    for concrete_step in concretized_plan.steps:
        source_step = plan_steps.get(concrete_step.technique_id)
        if source_step is None:
            raise ValueError(
                f"concretized technique absent from source plan: {concrete_step.technique_id}"
            )
        template = template_by_id.get(concrete_step.template_id)
        if template is None:
            raise ValueError(f"unknown template: {concrete_step.template_id}")
        extension = ProcedureSemantics(
            sequence=concrete_step.sequence,
            technique_id=concrete_step.technique_id,
            action_template_id=concrete_step.template_id,
            parameter_kinds=dict(template.parameter_kinds),
            requires=list(concrete_step.requires),
            produces=list(concrete_step.produces),
            evidence_predicates=list(concrete_step.evidence_predicates),
            fidelity_ceiling=concrete_step.fidelity_ceiling,
            proposal_source=concrete_step.proposal_source,
            provenance=FieldProvenance(
                origin=(
                    ValueOrigin.verified_llm_proposal
                    if concrete_step.proposal_source == "llm"
                    else ValueOrigin.finite_domain_solver
                ),
                source_ids=list(source_step.relationship_ids),
                source_sha256=concretized_plan.content_sha256,
                method="bounded proposal followed by deterministic verification",
            ),
        )
        extension.finalize_hash()
        technique = objects.get(source_step.technique_stix_id)
        if technique is None:
            raise ValueError(f"technique object absent: {source_step.technique_stix_id}")
        if technique["id"] not in included_techniques:
            output_objects.append(copy.deepcopy(technique))
            included_techniques.add(technique["id"])
        for relationship_id in source_step.relationship_ids:
            relationship = objects.get(relationship_id)
            if relationship is None:
                raise ValueError(f"relationship object absent: {relationship_id}")
            enriched = copy.deepcopy(relationship)
            enriched[PROCEDURE_PROPERTY] = extension.model_dump(mode="json")
            if relationship_id not in included_relationships:
                output_objects.append(enriched)
                included_relationships.add(relationship_id)

    digest = concretized_plan.content_sha256
    bundle_id = (
        f"bundle--{digest[:8]}-{digest[8:12]}-4{digest[13:16]}"
        f"-8{digest[17:20]}-{digest[20:32]}"
    )
    return {
        "type": "bundle",
        "id": bundle_id,
        "objects": output_objects,
        "x_sticks_export": {
            "schema_version": "1",
            "campaign_id": plan.campaign_id,
            "source_bundle_sha256": source_hash,
            "procedural_plan_sha256": plan.content_sha256,
            "concretized_plan_sha256": concretized_plan.content_sha256,
            "planning_certificate_sha256": (
                concretized_plan.planning_certificate.content_sha256
            ),
        },
    }

