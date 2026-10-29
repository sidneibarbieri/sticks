"""Build a bounded prompt that exposes references, never executable secrets."""

from __future__ import annotations

import json

from contracts.procedural_ir import ProceduralPlan

from .models import ActionTemplate, BindingCatalog
from .retrieval import retrieve_templates


SYSTEM_PROMPT = """You map structured CTI steps to a finite catalog of safe laboratory action templates.
You are an untrusted proposer: a deterministic verifier rejects anything outside the supplied
finite domain, so only well-formed, in-catalog proposals are useful.

Return JSON only, matching this exact schema:
  {"proposals": [
     {"technique_id": string,
      "template_id": string,                          // one of the supplied template IDs for the step
      "bindings": {parameter_name: binding_id, ...},  // a JSON object, never a list
      "rationale": string,
      "source": "llm"}
  ]}

Rules:
- bindings maps each template parameter to exactly one supplied binding ID. Every value is a
  non-null supplied binding ID; never a list, an object, or an invented value.
- Use only the supplied template IDs and binding IDs. Never emit shell commands, code, URLs,
  credentials, new hosts, or new parameter values.

Worked example (template "run-benign-python" declares parameters runtime and target):
  {"proposals": [
     {"technique_id": "T1059.006",
      "template_id": "run-benign-python",
      "bindings": {"runtime": "runtime.python3", "target": "target.primary"},
      "rationale": "Run a bounded benign command through the compromised service.",
      "source": "llm"}
  ]}"""


def build_prompt(
    plan: ProceduralPlan,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
) -> str:
    safe_bindings = [
        {
            "binding_id": binding.binding_id,
            "kind": binding.kind,
            "source": binding.source,
            "scope": binding.scope.value,
            "secret_reference": binding.secret_reference,
        }
        for binding in catalog.bindings
    ]
    retrieved_by_step = {}
    selected_template_ids = set()
    for step in plan.steps:
        retrieved, trace = retrieve_templates(step, templates)
        retrieved_by_step[step.technique_id] = [
            candidate.model_dump(mode="json") for candidate in trace.candidates
        ]
        selected_template_ids.update(
            template.template_id for template in retrieved
        )
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
        "initial_facts": catalog.initial_facts,
        "bindings": safe_bindings,
        "retrieval": retrieved_by_step,
        "templates": [
            template.model_dump(mode="json")
            for template in templates
            if template.template_id in selected_template_ids
        ],
    }
    return json.dumps(payload, sort_keys=True)
