"""Prepare a new causal plan under an explicitly pinned runtime order."""

import hashlib
import argparse
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from concretization.models import BindingCatalog, ConcretizedPlan
from concretization.planning import certify_plan
from evaluation.runtime_identity import expected_runtime_campaign


class RuntimeOrderRow(BaseModel):
    """Read only order and technique; executor qualification belongs to the bridge."""

    model_config = ConfigDict(frozen=True, extra="ignore")
    occurrence: int = Field(strict=True, gt=0)
    technique_id: str = Field(min_length=1)


class RuntimeOrderPopulation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    campaign_id: str = Field(min_length=1)
    occurrences: tuple[RuntimeOrderRow, ...] = Field(min_length=1)


def runtime_techniques(runtime_bytes: bytes, campaign_id: str) -> tuple[str, ...]:
    population = RuntimeOrderPopulation.model_validate_json(runtime_bytes)
    if population.campaign_id != expected_runtime_campaign(campaign_id):
        raise ValueError("Runtime campaign differs from selected plan")
    rows = sorted(population.occurrences, key=lambda row: row.occurrence)
    if [row.occurrence for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("Runtime occurrences must be unique and contiguous")
    techniques = tuple(row.technique_id for row in rows)
    if len(set(techniques)) != len(techniques):
        raise ValueError("Runtime techniques must be unique; repeated techniques need explicit identities")
    return techniques


def align_plan_to_runtime(
    plan: ConcretizedPlan, catalog: BindingCatalog, runtime_bytes: bytes,
) -> ConcretizedPlan:
    """Derive a new plan; never relabel a historical collection or repair its cells.

    This checks declared causal reachability, not observed effects or equivalence
    between a template and a selected executor. Freeze and review the new plan
    before collecting proposals or handing it to a runtime consumer.
    """
    if not catalog.validate_hash() or catalog.content_sha256 != plan.binding_catalog_sha256:
        raise ValueError("Binding catalog hash differs from the source plan")
    aligned = plan.model_copy(deep=True)
    aligned.finalize_hash()
    if aligned.content_sha256 != plan.content_sha256:
        raise ValueError("Source plan hash mismatch")
    if plan.unresolved_technique_ids:
        raise ValueError("Source plan contains unresolved techniques")
    techniques = runtime_techniques(runtime_bytes, plan.campaign_id)
    by_technique = {step.technique_id: step for step in aligned.steps}
    if len(by_technique) != len(aligned.steps) or set(by_technique) != set(techniques):
        raise ValueError("Plan and runtime require the same unique technique population")
    aligned.steps = [by_technique[technique].model_copy(update={"sequence": sequence})
                     for sequence, technique in enumerate(techniques, 1)]
    certificate = certify_plan(aligned.steps, initial_facts=catalog.initial_facts,
                               goal_facts=catalog.goal_facts)
    if not certificate.valid:
        raise ValueError("Runtime order fails declared causal prerequisites or goals")
    aligned.planning_certificate = certificate
    aligned.ordering_policy = "explicit_runtime_order:" + hashlib.sha256(runtime_bytes).hexdigest()
    aligned.finalize_hash()
    return aligned


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    plan = ConcretizedPlan.model_validate_json(arguments.plan.read_bytes())
    catalog = BindingCatalog.model_validate_json(arguments.catalog.read_bytes())
    aligned = align_plan_to_runtime(plan, catalog, arguments.runtime.read_bytes())
    with arguments.output.open('x') as destination:
        destination.write(aligned.model_dump_json(indent=2) + '\n')
    print(json.dumps({'source_plan_sha256': plan.content_sha256,
                      'aligned_plan_sha256': aligned.content_sha256,
                      'steps': len(aligned.steps),
                      'status': 'prepared_not_executed'}))


if __name__ == '__main__':
    main()
