from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import ActionTemplate, ConcretizedPlan
from contracts.procedural_ir import ProceduralPlan
from contracts.stix_campaign_export import export_campaign_bundle
from contracts.stix_procedure_extension import (
    PROCEDURE_PROPERTY,
    parse_procedure_property,
)


def test_c0045_extension_round_trip() -> None:
    plan = ProceduralPlan.model_validate_json(
        (PROJECT_ROOT / "release/plans/C0045.procedural-plan.json").read_text()
    )
    concrete = ConcretizedPlan.model_validate_json(
        (PROJECT_ROOT / "release/plans/C0045.concretized-plan.json").read_text()
    )
    template_payload = json.loads(
        (PROJECT_ROOT / "data/concretization/action_templates.json").read_text()
    )
    templates = [
        ActionTemplate.model_validate(item)
        for item in template_payload["templates"]
    ]
    bundle = export_campaign_bundle(
        source_bundle_path=PROJECT_ROOT / "data/stix/enterprise-attack.json",
        plan=plan,
        concretized_plan=concrete,
        templates=templates,
    )
    relationships = [
        item
        for item in bundle["objects"]
        if item.get("type") == "relationship" and PROCEDURE_PROPERTY in item
    ]
    assert len(relationships) == len(concrete.steps)
    parsed = [parse_procedure_property(item) for item in relationships]
    assert all(item is not None for item in parsed)
    assert sorted(item.sequence for item in parsed if item is not None) == list(
        range(1, len(concrete.steps) + 1)
    )

