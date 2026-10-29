"""How much catalog authoring STICKS needs, and how much of it a proposer can take over.

Reviewers ask what the manual step costs. Wall-clock analyst time would need a user
study, so this module measures the quantities that bound that cost deterministically:

- the authoring surface: the fields a person declares to make one template admissible;
- amortization: how many corpus steps each authored template then serves;
- automation: how many proposer drafts the deterministic gate admits without a person,
  and how many it rejects on its own.

Scope. None of these is a time or expertise measurement. Admitted drafts are
contract-valid, not executed, and stay review-pending.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from concretization.models import ActionTemplate


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TemplateSurface(StrictModel):
    template_id: str
    parameters: int
    requirements: int
    effects: int
    evidence_predicates: int

    @property
    def fields(self) -> int:
        return self.parameters + self.requirements + self.effects + self.evidence_predicates


class AutomationYield(StrictModel):
    proposals: int
    admitted: int
    rejected: int
    rejected_by_code: dict[str, int]


class AuthoringCost(StrictModel):
    templates: int
    total_fields: int
    median_fields: int
    max_fields: int
    covered_techniques: int
    covered_steps: int
    steps_per_template: float
    automation: AutomationYield


def template_surface(template: ActionTemplate) -> TemplateSurface:
    return TemplateSurface(
        template_id=template.template_id,
        parameters=len(template.parameter_kinds),
        requirements=len(template.requires),
        effects=len(template.produces),
        evidence_predicates=len(template.evidence_predicates),
    )


def _median(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def measure_authoring_cost(
    templates: list[ActionTemplate],
    step_counts: Mapping[str, int],
    automation: AutomationYield,
) -> AuthoringCost:
    """Combine the catalog's authoring surface, its reuse and the proposer's yield."""
    if not templates:
        raise ValueError("the catalog has no templates to measure")
    fields = [template_surface(template).fields for template in templates]
    covered = {technique for template in templates for technique in template.technique_ids}
    covered_steps = sum(count for technique, count in step_counts.items() if technique in covered)
    return AuthoringCost(
        templates=len(templates),
        total_fields=sum(fields),
        median_fields=_median(fields),
        max_fields=max(fields),
        covered_techniques=len(covered),
        covered_steps=covered_steps,
        steps_per_template=round(covered_steps / len(templates), 1),
        automation=automation,
    )
