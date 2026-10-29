"""Raw-STIX versus enriched baseline, under one admission pipeline.

Both arms run the identical solver and verifier and differ only in the environment:

  - Raw-STIX arm: the unaugmented ATT&CK-in-STIX representation. The procedural plan
    (techniques and a reconstructed order) is preserved; the declared laboratory -- concrete
    bindings and environment facts -- is removed. This is what direct use of ATT&CK-in-STIX
    offers a replay pipeline: technique-level content and no execution environment.
  - Enriched arm: the same plan against the declared environment (the reconstructed
    contracts).

A step counts as executable when the verifier admits a concretization for it. The result
compares admitted-step counts across the two arms. The raw arm is observed, not assigned:
it runs the same pipeline, so an unresolved step is a real admission outcome. The finding
is that technique-level CTI alone does not satisfy the pipeline's explicit execution
requirements; it does not imply that the source reports contain no procedural information,
and the enriched arm supplies the procedural commitments needed to instantiate the
CTI-described steps, not the steps themselves.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from concretization.models import ActionTemplate, BindingCatalog
from concretization.pipeline import concretize_plan
from contracts.procedural_ir import ProceduralPlan


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnrichmentBaseline(StrictModel):
    campaign_id: str
    total_steps: int
    raw_stix_executable_steps: int
    enriched_executable_steps: int
    # Steps executable only after the declared environment is supplied.
    enrichment_delta: int
    raw_stix_executable_rate: float
    enriched_executable_rate: float
    declared_catalog_sha256: str
    raw_catalog_sha256: str


def empty_environment(declared: BindingCatalog) -> BindingCatalog:
    """The raw-STIX environment: the same campaign catalog with no bindings and no facts."""
    raw = declared.model_copy(
        update={"bindings": [], "initial_facts": [], "goal_facts": []}
    )
    raw.finalize_hash()
    return raw


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def run_baseline(
    campaign_id: str,
    plan: ProceduralPlan,
    declared: BindingCatalog,
    templates: list[ActionTemplate],
) -> EnrichmentBaseline:
    raw = empty_environment(declared)
    raw_result = concretize_plan(plan, raw, templates, llm_proposals=[])
    enriched_result = concretize_plan(plan, declared, templates, llm_proposals=[])

    total_steps = len(plan.steps)
    raw_steps = len(raw_result.steps)
    enriched_steps = len(enriched_result.steps)
    return EnrichmentBaseline(
        campaign_id=campaign_id,
        total_steps=total_steps,
        raw_stix_executable_steps=raw_steps,
        enriched_executable_steps=enriched_steps,
        enrichment_delta=enriched_steps - raw_steps,
        raw_stix_executable_rate=_rate(raw_steps, total_steps),
        enriched_executable_rate=_rate(enriched_steps, total_steps),
        declared_catalog_sha256=declared.content_sha256,
        raw_catalog_sha256=raw.content_sha256,
    )
