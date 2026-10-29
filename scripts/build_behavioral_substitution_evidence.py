#!/usr/bin/env python3
"""Test whether verifier-admitted procedural realizations remain observably distinguishable.

Hypothesis: when the verifier admits more than one realization for the same CTI-derived
constraints, does admissibility alone determine observable behavior?

Answering it requires alternatives that are co-admitted at the scope that matters. This
script reports admissibility at all three scopes (see concretization.admissibility) and
records which scope produced the executed set, because the scope determines what the result
can claim:

  sequential multiplicity   a real alternative existed when the step ran; executing the
                            alternatives is a campaign-derived substitution experiment.
  hypothetical multiplicity only a catalog-level potential alternative; executing them
                            validates the execution and observation harness, and says
                            nothing about ambiguity in the evaluated campaign.

Each executed realization holds payload, bindings, initial state, and evidence predicates
constant; only the transport mechanism varies. Comparison uses the observed effect, never
declared produced-fact names. Process and network telemetry are not captured on the local
substrate, so effect-equivalent alternatives are reported as inconclusive rather than as
observational equivalence over the full behavioral surface.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from concretization.admissibility import (  # noqa: E402
    AdmissibilityScope,
    admitted_template_ids,
    hypothetical_facts,
    sequential_facts,
)
from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from concretization.pipeline import concretize_plan  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402
from evaluation.behavioral_substitution import (  # noqa: E402
    DimensionResult,
    Substrate,
    TemplateObservation,
    evaluate_step,
)
from executors.local_transport_realizations import (  # noqa: E402
    BENIGN_PAYLOAD,
    REALIZATIONS,
)

TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
PLANS_DIR = PROJECT_ROOT / "release" / "plans"
CAMPAIGN_ID = "C0045"
TECHNIQUE_ID = "T1105"
OUTPUT_DIR = PROJECT_ROOT / "release" / "experiments" / "behavioral_substitution"
OBSERVED_EFFECT = "destination_payload_present"


def admissibility_by_scope(campaign_id: str, technique_id: str) -> dict:
    """Templates the verifier admits for the campaign step, at each admissibility scope."""
    raw_templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    templates = [ActionTemplate.model_validate(item) for item in raw_templates]
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
    )
    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
    )
    step = next(item for item in plan.steps if item.technique_id == technique_id)
    committed = concretize_plan(plan, catalog, templates, llm_proposals=[]).steps

    facts_by_scope = {
        AdmissibilityScope.hypothetical: hypothetical_facts(catalog, templates),
        AdmissibilityScope.initial: set(catalog.initial_facts),
        AdmissibilityScope.sequential: sequential_facts(catalog, committed, technique_id),
    }
    return {
        scope: admitted_template_ids(step, templates, catalog, facts)
        for scope, facts in facts_by_scope.items()
    }


def _local_observer(workdir: Path):
    payload = workdir / "payload.bin"
    payload.write_bytes(BENIGN_PAYLOAD)
    payload_hash = hashlib.sha256(BENIGN_PAYLOAD).hexdigest()

    def observe(template_id: str) -> TemplateObservation:
        realization = REALIZATIONS[template_id]
        # Each alternative delivers to an identically named destination in its own
        # subdirectory, so the destination name cannot leak template identity into the
        # observed effect. Only the transport mechanism varies across alternatives.
        subdir = workdir / template_id
        subdir.mkdir()
        destination = subdir / "delivered.bin"
        result = realization(payload, destination)
        return TemplateObservation(
            template_id=template_id,
            substrate=Substrate.local,
            executed=True,
            exit_code=result.exit_code,
            evidence_predicate_satisfied=result.destination_sha256 == payload_hash,
            produced_effects=[OBSERVED_EFFECT],
            host_artifacts=sorted(result.created_files),
            telemetry=DimensionResult.not_instrumented,
            detection=DimensionResult.not_instrumented,
        )

    return observe


def main() -> int:
    admitted = admissibility_by_scope(CAMPAIGN_ID, TECHNIQUE_ID)
    sequential = admitted[AdmissibilityScope.sequential]
    hypothetical = admitted[AdmissibilityScope.hypothetical]

    # Only sequential multiplicity makes this a campaign-derived substitution experiment.
    if len(sequential) > 1:
        executed_scope, executed = AdmissibilityScope.sequential, sequential
    else:
        executed_scope, executed = AdmissibilityScope.hypothetical, hypothetical

    unrealized = [tid for tid in executed if tid not in REALIZATIONS]
    if unrealized:
        raise RuntimeError(f"no local realization for admitted templates: {unrealized}")

    with tempfile.TemporaryDirectory() as tmp:
        step = evaluate_step(
            campaign_id=CAMPAIGN_ID,
            technique_id=TECHNIQUE_ID,
            execution_domain="boundary",
            admissible_template_ids=executed,
            observe=_local_observer(Path(tmp)),
        )

    record = step.model_dump(mode="json")
    record["admitted_by_scope"] = {scope.value: ids for scope, ids in admitted.items()}
    record["executed_scope"] = executed_scope.value
    record["is_campaign_derived_substitution"] = len(sequential) > 1
    record["interpretation"] = (
        "campaign-derived substitution: the verifier admitted multiple realizations at the "
        "step's sequential state"
        if len(sequential) > 1
        else "harness validation: the verifier admitted a single realization at the step's "
        "sequential state, so the executed alternatives are co-admitted only under the "
        "hypothetical scope and carry no claim about ambiguity in this campaign"
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{TECHNIQUE_ID}.substitution.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    for scope, ids in admitted.items():
        print(f"  {scope.value:13s} admitted={len(ids)} {ids}")
    print(f"executed at scope: {executed_scope.value} -> {step.classification.value}")
    print(f"  {record['interpretation']}")
    print(f"[behavioral-substitution] wrote {TECHNIQUE_ID}.substitution.json to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
