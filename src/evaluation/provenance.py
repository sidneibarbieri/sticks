"""Per-decision provenance over a concretized plan: what the report supplied versus
what the reconstruction introduced.

This attributes every execution decision from the contract's own authoritative record --
STICKS's internal provenance, produced by deterministic rules and validated by the
verifier. It is not a claim that the attribution matches the campaign's historical
reality; it records where each value came from within the reconstruction.

Frozen definitions (taxonomy version below; see release/experiments/provenance/TAXONOMY.md):

  1. Executable binding -- the unit of decision. One (template parameter -> binding_id)
     pair required to concretize a step. A binding_id reused across steps is a separate
     decision at each step, so the primary counts are per-occurrence; the distinct
     binding_id view is reported separately.
  2. Source attribution -- deterministic, no manual annotation. Each binding carries a
     declared ``source`` in the contract; its class is a fixed function of that field:
     stix->cti_evidenced, sut->environment_determined, executor->runtime_derived, and
     anything else (e.g. system_choice)->system_introduced.
  3. Denominator -- the primary rates are over total binding occurrences across all
     concretized steps; the unique view is over distinct binding_ids.
  4. Counting -- per-occurrence for the primary rates: a value used in three steps counts
     three times, because each step is a separate execution decision to attribute.

``system_introduced`` denotes provenance, not behavioral invention or low fidelity: a
benign toolkit, a lab host identity, or a synthetic credential is introduced by the
system but is not a hypothesis about adversary behavior. ``environment_determined`` values
come from the declared laboratory, not a free reconstruction choice, and are reported
separately -- the two must not be grouped.

Mechanism provenance is reported separately from binding provenance and is a
characterization of the current design, not an outcome claim. ``proposer_chosen`` marks a
step that admits more than one template with distinct declared certified effects -- the
only place an untrusted proposer could select a different declared effect. A zero rate
means mechanism selection was contract-constrained rather than proposer-selected in the
evaluated workflows; it does not establish that alternative templates would produce
identical observed behavior, which is an execution-level validation question.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from .substitution import StepClass, classify_step

TAXONOMY_VERSION = "1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BindingProvenance(str, Enum):
    cti_evidenced = "cti_evidenced"
    environment_determined = "environment_determined"
    runtime_derived = "runtime_derived"
    system_introduced = "system_introduced"


class MechanismProvenance(str, Enum):
    contract_forced = "contract_forced"
    proposer_chosen = "proposer_chosen"


# The closed set of binding sources and the class each maps to. Extending it is a
# deliberate taxonomy change, not a silent default.
BINDING_SOURCE_CLASSES: dict[str, BindingProvenance] = {
    "stix": BindingProvenance.cti_evidenced,
    "sut": BindingProvenance.environment_determined,
    "executor": BindingProvenance.runtime_derived,
    "system_choice": BindingProvenance.system_introduced,
}


def classify_binding(source: str) -> BindingProvenance:
    """Map a declared binding source to its provenance class.

    Fail-closed: an unrecognized source raises rather than falling into a default class,
    so a new source must be classified deliberately.
    """
    if source not in BINDING_SOURCE_CLASSES:
        raise ValueError(
            f"unrecognized binding source {source!r}; add it to BINDING_SOURCE_CLASSES "
            "as a deliberate taxonomy change"
        )
    return BINDING_SOURCE_CLASSES[source]


def classify_mechanism(
    technique_id: str,
    execution_domain: str,
    templates: list[dict[str, Any]],
) -> MechanismProvenance:
    step_class = classify_step(technique_id, execution_domain, templates)
    if step_class is StepClass.evidence_divergent:
        return MechanismProvenance.proposer_chosen
    return MechanismProvenance.contract_forced


class BindingDecision(StrictModel):
    parameter: str
    binding_id: str
    provenance: BindingProvenance


class StepProvenance(StrictModel):
    sequence: int
    technique_id: str
    template_id: str
    mechanism: MechanismProvenance
    bindings: list[BindingDecision]


class CampaignProvenance(StrictModel):
    taxonomy_version: str
    campaign_id: str
    total_steps: int
    # Primary denominator: every (parameter -> binding) decision, counted per occurrence.
    total_binding_occurrences: int
    binding_occurrence_counts: dict[BindingProvenance, int]
    # Secondary view: distinct binding_ids used anywhere in the plan.
    unique_binding_count: int
    unique_binding_counts: dict[BindingProvenance, int]
    mechanism_counts: dict[MechanismProvenance, int]
    # Rates below are over binding occurrences (definition 3).
    cti_binding_rate: float
    environment_binding_rate: float
    system_introduced_rate: float
    # Characterization of the current design, not an outcome claim (see module docstring).
    proposer_chosen_mechanism_rate: float
    steps: list[StepProvenance]


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def analyze_plan(
    campaign_id: str,
    concretized_steps: list[dict[str, Any]],
    catalog_bindings: list[dict[str, Any]],
    templates: list[dict[str, Any]],
) -> CampaignProvenance:
    binding_source = {b["binding_id"]: b["source"] for b in catalog_bindings}
    template_domain = {t["template_id"]: t["execution_domain"] for t in templates}

    step_records: list[StepProvenance] = []
    mechanism_counts = {member: 0 for member in MechanismProvenance}
    occurrence_counts = {member: 0 for member in BindingProvenance}
    unique_provenance: dict[str, BindingProvenance] = {}

    for step in concretized_steps:
        mechanism = classify_mechanism(
            step["technique_id"], template_domain[step["template_id"]], templates
        )
        mechanism_counts[mechanism] += 1
        decisions: list[BindingDecision] = []
        for parameter, binding_id in sorted(step["bindings"].items()):
            provenance = classify_binding(binding_source[binding_id])
            occurrence_counts[provenance] += 1
            unique_provenance[binding_id] = provenance
            decisions.append(
                BindingDecision(
                    parameter=parameter, binding_id=binding_id, provenance=provenance
                )
            )
        step_records.append(
            StepProvenance(
                sequence=step["sequence"],
                technique_id=step["technique_id"],
                template_id=step["template_id"],
                mechanism=mechanism,
                bindings=decisions,
            )
        )

    unique_counts = {member: 0 for member in BindingProvenance}
    for provenance in unique_provenance.values():
        unique_counts[provenance] += 1

    total_steps = len(concretized_steps)
    total_occurrences = sum(occurrence_counts.values())
    return CampaignProvenance(
        taxonomy_version=TAXONOMY_VERSION,
        campaign_id=campaign_id,
        total_steps=total_steps,
        total_binding_occurrences=total_occurrences,
        binding_occurrence_counts=occurrence_counts,
        unique_binding_count=len(unique_provenance),
        unique_binding_counts=unique_counts,
        mechanism_counts=mechanism_counts,
        cti_binding_rate=_rate(
            occurrence_counts[BindingProvenance.cti_evidenced], total_occurrences
        ),
        environment_binding_rate=_rate(
            occurrence_counts[BindingProvenance.environment_determined], total_occurrences
        ),
        system_introduced_rate=_rate(
            occurrence_counts[BindingProvenance.system_introduced], total_occurrences
        ),
        proposer_chosen_mechanism_rate=_rate(
            mechanism_counts[MechanismProvenance.proposer_chosen], total_steps
        ),
        steps=step_records,
    )
