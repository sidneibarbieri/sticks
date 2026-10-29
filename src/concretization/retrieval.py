"""Deterministic retrieval over the versioned safe-action catalog."""

from __future__ import annotations

import hashlib
import json
import re

from contracts.procedural_ir import ProcedureStep

from .models import ActionTemplate, RetrievedTemplate, RetrievalTrace


TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*")


def _tokens(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(text.lower()))


def index_hash(templates: list[ActionTemplate]) -> str:
    payload = [template.model_dump(mode="json") for template in templates]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def retrieve_templates(
    step: ProcedureStep,
    templates: list[ActionTemplate],
    *,
    top_k: int = 5,
) -> tuple[list[ActionTemplate], RetrievalTrace]:
    query_payload = {
        "technique_id": step.technique_id,
        "name": step.name,
        "execution_domain": step.execution_domain,
        "tactics": step.tactics,
        "platforms": step.platforms,
        "procedure_descriptions": step.procedure_descriptions,
    }
    query_encoded = json.dumps(
        query_payload, sort_keys=True, separators=(",", ":")
    ).encode()
    query_terms = _tokens(
        " ".join(
            [
                step.technique_id,
                step.name,
                *step.tactics,
                *step.platforms,
                *step.procedure_descriptions,
            ]
        )
    )
    scored: list[tuple[ActionTemplate, RetrievedTemplate]] = []
    for template in templates:
        exact = step.technique_id in template.technique_ids
        domain_match = step.execution_domain == template.execution_domain
        template_terms = _tokens(
            " ".join(
                [
                    template.template_id,
                    template.description,
                    *template.technique_ids,
                    *template.requires,
                    *template.produces,
                ]
            )
        )
        shared = sorted(query_terms & template_terms)
        score = (1000 if exact else 0) + (100 if domain_match else 0) + len(shared)
        if score > 0:
            scored.append(
                (
                    template,
                    RetrievedTemplate(
                        template_id=template.template_id,
                        score=score,
                        exact_technique_match=exact,
                        domain_match=domain_match,
                        shared_terms=shared,
                    ),
                )
            )
    scored.sort(key=lambda item: (-item[1].score, item[0].template_id))
    selected = scored[:top_k]
    trace = RetrievalTrace(
        technique_id=step.technique_id,
        query_sha256=hashlib.sha256(query_encoded).hexdigest(),
        index_sha256=index_hash(templates),
        candidates=[item[1] for item in selected],
    )
    return [item[0] for item in selected], trace
