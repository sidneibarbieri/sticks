"""Generate a bounded, auditable batch of untrusted action-template candidates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import Field

from .models import ActionTemplate, StrictModel
from .pipeline import action_catalog_hash
from .provider import (
    BudgetLedger,
    ProviderConfig,
    RawCompletionRecord,
    complete_raw,
)
from .template_admission import build_admission_vocabulary
from .template_proposer import (
    TemplateProposalContext,
    TemplateProposalOutcome,
    propose_template,
)


class TemplateGenerationTarget(StrictModel):
    target_id: str | None = Field(default=None, min_length=1)
    technique_id: str = Field(pattern=r"^T\d{4}(\.\d{3})?$")
    technique_summary: str = Field(min_length=1)
    exemplar_template_ids: list[str] = Field(default_factory=list)
    context: TemplateProposalContext | None = None


class TemplateGenerationRow(StrictModel):
    target: TemplateGenerationTarget
    outcome: TemplateProposalOutcome
    calls: list[RawCompletionRecord] = Field(default_factory=list)


class CandidateContextBinding(StrictModel):
    """Bind one admitted candidate to its hash-pinned proposal context."""

    candidate_template_id: str
    target_id: str
    technique_id: str = Field(pattern=r"^T\d{4}(\.\d{3})?$")
    context: TemplateProposalContext


class TemplateGenerationBatch(StrictModel):
    schema_version: str = "1"
    base_action_catalog_sha256: str
    provider: str
    model: str
    max_attempts_per_target: int = Field(ge=1)
    target_count: int = Field(ge=0)
    admitted_count: int = Field(ge=0)
    request_count: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    estimated_usd: float = Field(ge=0)
    rows: list[TemplateGenerationRow] = Field(default_factory=list)
    templates: list[ActionTemplate] = Field(default_factory=list)
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.content_sha256 = hashlib.sha256(encoded).hexdigest()

    def validate_hash(self) -> bool:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return bool(self.content_sha256) and self.content_sha256 == hashlib.sha256(
            encoded
        ).hexdigest()


def context_bindings_from_generation_batch(
    batch: TemplateGenerationBatch,
) -> list[CandidateContextBinding]:
    """Extract one context binding per admitted candidate or fail closed."""

    if not batch.validate_hash():
        raise ValueError("template generation batch hash mismatch")
    if batch.target_count != len(batch.rows):
        raise ValueError("template generation batch target count does not match its rows")
    admitted_rows = [
        row
        for row in batch.rows
        if row.outcome.admitted and row.outcome.template is not None
    ]
    if batch.admitted_count != len(admitted_rows):
        raise ValueError("template generation batch admitted count does not match its rows")
    admitted_templates = [row.outcome.template for row in admitted_rows]
    if admitted_templates != batch.templates:
        raise ValueError("template generation batch templates do not match admitted rows")
    bindings: list[CandidateContextBinding] = []
    for row in admitted_rows:
        context = row.target.context
        if context is None:
            raise ValueError("admitted candidate lacks a hash-pinned proposal context")
        if not context.validate_hash():
            raise ValueError("candidate proposal context hash mismatch")
        target_id = row.target.target_id
        if target_id is None:
            raise ValueError("admitted candidate target lacks a stable identifier")
        bindings.append(
            CandidateContextBinding(
                candidate_template_id=row.outcome.template.template_id,
                target_id=target_id,
                technique_id=row.target.technique_id,
                context=context,
            )
        )
    candidate_ids = [binding.candidate_template_id for binding in bindings]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("admitted candidate template identifiers must be unique")
    return bindings


def _exemplars(
    target: TemplateGenerationTarget,
    templates: list[ActionTemplate],
    *,
    default_count: int = 5,
) -> list[ActionTemplate]:
    template_index = {template.template_id: template for template in templates}
    if target.exemplar_template_ids:
        unknown = sorted(set(target.exemplar_template_ids) - set(template_index))
        if unknown:
            raise ValueError("unknown exemplar template ids: " + ", ".join(unknown))
        return [template_index[template_id] for template_id in target.exemplar_template_ids]
    return sorted(templates, key=lambda template: template.template_id)[:default_count]


def generate_template_candidates(
    targets: list[TemplateGenerationTarget],
    base_templates: list[ActionTemplate],
    config: ProviderConfig,
    *,
    output_dir: Path,
    max_attempts_per_target: int = 3,
) -> TemplateGenerationBatch:
    """Generate candidates while keeping proposal, admission, and promotion separate."""

    if max_attempts_per_target < 1:
        raise ValueError("max_attempts_per_target must be positive")
    target_ids = [target.target_id or target.technique_id for target in targets]
    if len(target_ids) != len(set(target_ids)):
        raise ValueError("template generation targets must be unique")
    output_dir.mkdir(parents=True, exist_ok=False)
    vocabulary = build_admission_vocabulary(base_templates)
    budget = BudgetLedger(config.budget)
    rows: list[TemplateGenerationRow] = []
    admitted_templates: list[ActionTemplate] = []
    for target_index, target in enumerate(targets):
        call_records: list[RawCompletionRecord] = []

        def complete(system_prompt: str, user_prompt: str) -> str:
            attempt = len(call_records) + 1
            content, record = complete_raw(
                config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_dir=output_dir / f"target-{target_index:03d}" / f"attempt-{attempt:02d}",
                budget=budget,
            )
            call_records.append(record)
            return content

        outcome = propose_template(
            target.technique_id,
            target.technique_summary,
            vocabulary,
            _exemplars(target, base_templates),
            complete,
            max_attempts=max_attempts_per_target,
            context=target.context,
        )
        rows.append(
            TemplateGenerationRow(
                target=target,
                outcome=outcome,
                calls=call_records,
            )
        )
        if outcome.admitted and outcome.template is not None:
            admitted_templates.append(outcome.template)
    result = TemplateGenerationBatch(
        base_action_catalog_sha256=action_catalog_hash(
            sorted(base_templates, key=lambda template: template.template_id)
        ),
        provider=config.provider.value,
        model=config.model,
        max_attempts_per_target=max_attempts_per_target,
        target_count=len(targets),
        admitted_count=len(admitted_templates),
        request_count=budget.requests,
        prompt_tokens=budget.prompt_tokens,
        completion_tokens=budget.completion_tokens,
        estimated_usd=round(budget.estimated_usd, 8),
        rows=rows,
        templates=admitted_templates,
    )
    result.finalize_hash()
    return result
