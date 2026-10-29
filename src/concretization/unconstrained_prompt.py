"""Prompt for the unconstrained reconstruction arm: no catalog, no verifier.

This arm models the conventional practice the paper argues against: an analyst (or model)
reads a CTI step and writes the concrete executable realization directly, choosing the
mechanism and its parameters freely. It is the counterfactual to the finite-domain arm, so it
must be matched in every respect except the removed variable. The proposer sees the same
campaign steps and the same declared laboratory environment; it does not see an action
catalog and its output is not admitted by a verifier.

The output is structured so reconstructions can be compared at the decision level rather than
as free text: the divergence of interest is which mechanism and which concrete values each
proposer commits, not surface wording.
"""

from __future__ import annotations

import json

from contracts.procedural_ir import ProceduralPlan

from .models import BindingCatalog

SYSTEM_PROMPT_UNCONSTRAINED = """You are a red-team engineer turning a documented CTI technique into a concrete, runnable step for a declared laboratory. There is no menu of pre-approved actions: you choose the mechanism and its parameters yourself, exactly as an analyst writing the emulation by hand would.

For each step, decide how you would realize the technique in the declared environment and return JSON only, matching this exact schema:
  {"realizations": [
     {"technique_id": string,
      "mechanism": string,     // short label for the concrete method you chose, e.g. "certutil-download" or "scheduled-task-persistence"
      "command": string,       // the concrete command or action you would run
      "target": string,        // which declared host or service it runs against
      "parameters": {name: value, ...}}  // concrete values your command needs (paths, ports, urls, ...)
  ]}

Rules:
- Choose the mechanism you judge most appropriate; there is no fixed catalog to select from.
- Bind the target to one of the declared environment hosts or services when applicable.
- Fill parameters with the concrete values your command would actually use.
- Return one realization per supplied step, in the same order."""


def build_unconstrained_prompt(
    plan: ProceduralPlan,
    catalog: BindingCatalog,
) -> str:
    """Serialize the same steps and declared environment the finite-domain arm receives.

    The action catalog and retrieval traces are deliberately omitted: this arm removes the
    finite domain and keeps everything else fixed.
    """
    environment = [
        {
            "binding_id": binding.binding_id,
            "kind": binding.kind,
            "scope": binding.scope.value,
        }
        for binding in catalog.bindings
    ]
    payload = {
        "campaign_id": plan.campaign_id,
        "steps": [
            {
                "technique_id": step.technique_id,
                "name": step.name,
                "execution_domain": step.execution_domain,
                "tactics": step.tactics,
                "platforms": step.platforms,
                "procedure_descriptions": step.procedure_descriptions,
            }
            for step in plan.steps
        ],
        "declared_environment": environment,
        "initial_facts": catalog.initial_facts,
    }
    return json.dumps(payload, sort_keys=True)
