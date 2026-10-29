"""Produce a causal reachability certificate for a concretized plan."""

from __future__ import annotations

import hashlib
import json

from .models import (
    CausalLink,
    ConcretizedStep,
    PlanningCertificate,
    PlanningTransition,
)


def _state_hash(facts: set[str]) -> str:
    encoded = json.dumps(sorted(facts), separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def certify_plan(
    steps: list[ConcretizedStep],
    *,
    initial_facts: list[str],
    goal_facts: list[str],
) -> PlanningCertificate:
    state = set(initial_facts)
    producer = {fact_id: 0 for fact_id in state}
    transitions: list[PlanningTransition] = []
    links: list[CausalLink] = []
    valid = True
    for step in steps:
        missing = set(step.requires) - state
        if missing:
            valid = False
            continue
        before = _state_hash(state)
        for fact_id in step.requires:
            links.append(
                CausalLink(
                    fact_id=fact_id,
                    producer_sequence=producer[fact_id],
                    consumer_sequence=step.sequence,
                )
            )
        added = sorted(set(step.produces) - state)
        state.update(step.produces)
        for fact_id in step.produces:
            producer[fact_id] = step.sequence
        transitions.append(
            PlanningTransition(
                sequence=step.sequence,
                technique_id=step.technique_id,
                state_before_sha256=before,
                state_after_sha256=_state_hash(state),
                added_facts=added,
            )
        )
    unresolved = sorted(set(goal_facts) - state)
    certificate = PlanningCertificate(
        initial_facts=sorted(initial_facts),
        goal_facts=sorted(goal_facts),
        transitions=transitions,
        causal_links=links,
        final_facts=sorted(state),
        unresolved_goals=unresolved,
        valid=valid and not unresolved and len(transitions) == len(steps),
    )
    certificate.finalize_hash()
    return certificate
