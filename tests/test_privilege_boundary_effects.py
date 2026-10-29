"""A privilege assessment cannot authorize a later privileged transition."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import ActionTemplate, ConcretizedStep  # noqa: E402
from concretization.planning import certify_plan  # noqa: E402


def test_assessment_does_not_satisfy_privileged_action():
    payload = json.loads(
        (PROJECT_ROOT / "data/concretization/action_templates.json").read_text()
    )
    template = next(
        ActionTemplate.model_validate(item)
        for item in payload["templates"]
        if item["template_id"] == "assess-privilege-boundary"
    )
    assessment = ConcretizedStep(
        sequence=1, technique_id="T1068", template_id=template.template_id,
        bindings={}, requires=template.requires, produces=template.produces,
        evidence_predicates=template.evidence_predicates,
        fidelity_ceiling=template.fidelity_ceiling,
        proposal_source="finite_domain_solver", assumption_count=0,
    )
    privileged = assessment.model_copy(update={
        "sequence": 2, "template_id": "test-privileged-action",
        "requires": ["system:root_access"], "produces": ["privileged.effect"],
    })
    certificate = certify_plan(
        [assessment, privileged], initial_facts=template.requires,
        goal_facts=["privileged.effect"],
    )
    assert not certificate.valid
    assert certificate.unresolved_goals == ["privileged.effect"]
    assert "system:root_access" not in certificate.final_facts
    assert "access:privileged" not in certificate.final_facts
