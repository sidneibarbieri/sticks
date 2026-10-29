"""Formal definition of *procedural behavior*, the object STICKS produces.

The term is defined by the components an element must carry to be executable and
verifiable, so it is distinguishable -- mechanically, not rhetorically -- from a bare
ATT&CK technique (a TTP) and from a MITRE Attack Flow node.

A procedural-behavior element is the tuple

    (technique_identity, execution_order, causal_preconditions,
     causal_postconditions, verification, execution_grounding)

where every component is present:

  - technique_identity   the ATT&CK technique the step realizes (shared with a TTP).
  - execution_order      the step's position in the campaign sequence.
  - causal_preconditions facts that must hold before the step (its ``requires``).
  - causal_postconditions facts the step establishes (its ``produces``).
  - verification         a declared observable effect that certifies success
                         (``evidence_predicates``, non-empty).
  - execution_grounding  concrete laboratory bindings for the step's parameters
                         (non-empty).

The definition is positive: an element is procedural behavior when it carries all six
components. The comparison with adjacent representations is stated narrowly, in terms of
two components STICKS requires that a technique-and-flow representation does not, by itself,
guarantee -- executable grounding and effect verification:

  - A **TTP** (an ATT&CK technique in STIX) carries technique identity; it is descriptive
    and does not, on its own, provide order, bindings, or a success predicate.
  - **MITRE Attack Flow** represents relationships and sequencing among adversary actions
    (order, and conditions/assets). STICKS additionally requires bindings to an executable
    environment and evidence predicates for validating the expected effect; these two are
    the components the comparison focuses on.

``assess_element`` is a predicate over a mapping, so it applies uniformly to a STICKS
concretized step and to canonical representatives of the other representations. Those
representatives model documented capabilities of each representation; they are not a claim
about every possible profile a representation could take.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BehaviorComponent(str, Enum):
    technique_identity = "technique_identity"
    execution_order = "execution_order"
    causal_preconditions = "causal_preconditions"
    causal_postconditions = "causal_postconditions"
    verification = "verification"
    execution_grounding = "execution_grounding"


REQUIRED_COMPONENTS: tuple[BehaviorComponent, ...] = tuple(BehaviorComponent)


class ProceduralBehaviorAssessment(StrictModel):
    present: list[BehaviorComponent]
    missing: list[BehaviorComponent]
    is_procedural_behavior: bool


def _models_field(element: dict[str, Any], key: str) -> bool:
    """The representation models the field if it is present as a list (possibly empty)."""
    return isinstance(element.get(key), list)


def _declares_value(element: dict[str, Any], key: str) -> bool:
    """The element declares a non-empty value for the field."""
    value = element.get(key)
    return isinstance(value, (list, dict, str)) and len(value) > 0


def _component_present(element: dict[str, Any], component: BehaviorComponent) -> bool:
    if component is BehaviorComponent.technique_identity:
        return _declares_value(element, "technique_id")
    if component is BehaviorComponent.execution_order:
        sequence = element.get("sequence")
        return isinstance(sequence, int) and sequence > 0
    if component is BehaviorComponent.causal_preconditions:
        return _models_field(element, "requires")
    if component is BehaviorComponent.causal_postconditions:
        return _models_field(element, "produces")
    if component is BehaviorComponent.verification:
        return _declares_value(element, "evidence_predicates")
    if component is BehaviorComponent.execution_grounding:
        return _declares_value(element, "bindings")
    raise ValueError(f"unhandled component {component}")


def assess_element(element: dict[str, Any]) -> ProceduralBehaviorAssessment:
    present = [c for c in REQUIRED_COMPONENTS if _component_present(element, c)]
    missing = [c for c in REQUIRED_COMPONENTS if c not in present]
    return ProceduralBehaviorAssessment(
        present=present,
        missing=missing,
        is_procedural_behavior=not missing,
    )
