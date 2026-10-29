"""Budgeted LLM providers for candidate proposal, never direct execution."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, List, Optional, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .models import ProcedureProposal


class ProviderKind(str, Enum):
    azure_openai = "azure_openai"
    openai = "openai"
    anthropic = "anthropic"
    replay = "replay"


class BudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_requests: int = Field(default=20, ge=1)
    max_prompt_tokens: int = Field(default=100000, ge=1)
    max_completion_tokens: int = Field(default=24000, ge=1)
    max_estimated_usd: float = Field(default=5.0, ge=0)
    input_usd_per_million_tokens: float = Field(default=0.0, ge=0)
    output_usd_per_million_tokens: float = Field(default=0.0, ge=0)


def _is_loopback_endpoint(base_url: Optional[str]) -> bool:
    """True when the endpoint serves the model from this host, so no token is billed."""
    if not base_url:
        return False
    host = urlparse(base_url).hostname or ""
    return host in {"localhost", "127.0.0.1", "::1"}


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderKind
    model: str
    deployment: Optional[str] = None
    base_url: Optional[str] = None
    api_version: str = "2024-02-15-preview"
    api_key_env: str
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=1200, ge=1)
    timeout_seconds: int = Field(default=60, ge=1)
    replay_path: Optional[str] = None
    budget: BudgetConfig = Field(default_factory=BudgetConfig)

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "ProviderConfig":
        if self.provider == ProviderKind.azure_openai:
            if not self.base_url or not self.deployment:
                raise ValueError("Azure OpenAI requires base_url and deployment")
        if self.provider == ProviderKind.replay and not self.replay_path:
            raise ValueError("replay provider requires replay_path")
        # A metered provider must price its tokens so the budget can be enforced. Replay reads a
        # recorded transcript, and a loopback endpoint runs the model on this host, so neither
        # bills per token and neither can be priced.
        metered = self.provider != ProviderKind.replay and not _is_loopback_endpoint(self.base_url)
        if metered and (
            self.budget.input_usd_per_million_tokens <= 0
            or self.budget.output_usd_per_million_tokens <= 0
        ):
            raise ValueError(
                "metered providers require positive input and output token prices for budget enforcement"
            )
        return self


class ArtifactConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    llm: ProviderConfig


class UsageRecord(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_usd: float = 0.0


class LLMCallRecord(BaseModel):
    schema_version: str = "1"
    provider: str
    model: str
    request_sha256: str
    response_sha256: str
    usage: UsageRecord
    proposals: List[ProcedureProposal]
    malformed_proposals: int = 0
    raw_response_path: Optional[str] = None
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.content_sha256 = hashlib.sha256(encoded).hexdigest()


class RawCompletionRecord(BaseModel):
    schema_version: str = "1"
    provider: str
    model: str
    request_sha256: str
    response_sha256: str
    usage: UsageRecord
    raw_response_path: str
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.content_sha256 = hashlib.sha256(encoded).hexdigest()


class BudgetLedger:
    def __init__(self, config: BudgetConfig):
        self.config = config
        self.requests = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.estimated_usd = 0.0

    def ensure_request_capacity(self) -> None:
        if self.requests >= self.config.max_requests:
            raise RuntimeError("LLM request budget exceeded")

    def ensure_usage_capacity(self, usage: UsageRecord) -> None:
        next_requests = self.requests + 1
        next_prompt = self.prompt_tokens + usage.prompt_tokens
        next_completion = self.completion_tokens + usage.completion_tokens
        next_cost = self.estimated_usd + usage.estimated_usd
        if next_requests > self.config.max_requests:
            raise RuntimeError("LLM request budget exceeded")
        if next_prompt > self.config.max_prompt_tokens:
            raise RuntimeError("LLM prompt-token budget exceeded")
        if next_completion > self.config.max_completion_tokens:
            raise RuntimeError("LLM completion-token budget exceeded")
        if next_cost > self.config.max_estimated_usd:
            raise RuntimeError("LLM estimated-cost budget exceeded")

    def record(self, usage: UsageRecord) -> None:
        self.ensure_usage_capacity(usage)
        next_requests = self.requests + 1
        next_prompt = self.prompt_tokens + usage.prompt_tokens
        next_completion = self.completion_tokens + usage.completion_tokens
        next_cost = self.estimated_usd + usage.estimated_usd
        self.requests = next_requests
        self.prompt_tokens = next_prompt
        self.completion_tokens = next_completion
        self.estimated_usd = next_cost


def load_config(path: Path) -> ProviderConfig:
    return ArtifactConfig.model_validate_json(path.read_text(encoding="utf-8")).llm


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _request_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=_json_bytes(payload),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            decoded: object = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM provider HTTP {error.code}: {body[:500]}") from error
    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        raise ValueError("LLM provider response must be a JSON object with string keys")
    return cast(dict[str, Any], decoded)


def _extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]).strip()
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be one JSON object")
    return payload


def _parse_proposals(parsed: dict[str, Any]) -> tuple[List[ProcedureProposal], int]:
    """Keep the well-formed proposals and count the rest.

    A proposer is untrusted: it may emit a non-list, or items missing fields. Such output is
    not a usable candidate, so it is dropped here rather than raised -- the same rejection the
    verifier performs semantically, applied structurally at the boundary. The count is
    returned so the discard is recorded, never silent. Transport and JSON-decode failures
    still raise upstream.
    """
    raw = parsed.get("proposals", [])
    if not isinstance(raw, list):
        return [], 1
    proposals: List[ProcedureProposal] = []
    malformed = 0
    for item in raw:
        if not isinstance(item, dict):
            malformed += 1
            continue
        try:
            proposals.append(ProcedureProposal.model_validate(item))
        except ValidationError:
            malformed += 1
    return proposals, malformed


def _usage(config: ProviderConfig, prompt: int, completion: int) -> UsageRecord:
    cost = (
        prompt * config.budget.input_usd_per_million_tokens
        + completion * config.budget.output_usd_per_million_tokens
    ) / 1_000_000
    return UsageRecord(
        prompt_tokens=prompt,
        completion_tokens=completion,
        estimated_usd=round(cost, 8),
    )


def _maximum_request_usage(
    config: ProviderConfig,
    system_prompt: str,
    user_prompt: str,
) -> UsageRecord:
    """Return a conservative request reservation before an online call is made."""

    prompt_upper_bound = len(system_prompt.encode("utf-8")) + len(user_prompt.encode("utf-8"))
    return _usage(config, prompt_upper_bound, config.max_output_tokens)


def _ensure_call_capacity(
    config: ProviderConfig,
    system_prompt: str,
    user_prompt: str,
    budget: Optional[BudgetLedger],
) -> None:
    if budget is None:
        return
    budget.ensure_request_capacity()
    if config.provider != ProviderKind.replay:
        budget.ensure_usage_capacity(
            _maximum_request_usage(config, system_prompt, user_prompt)
        )


def require_credential(config: ProviderConfig) -> str:
    """Return the provider credential, failing before any run state is created."""
    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        raise RuntimeError(f"required provider credential is absent: {config.api_key_env}")
    return api_key


def _online_call(
    config: ProviderConfig,
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, UsageRecord, dict[str, Any]]:
    api_key = require_credential(config)
    if config.provider == ProviderKind.azure_openai:
        base_url = str(config.base_url).rstrip("/")
        deployment = urllib.parse.quote(str(config.deployment), safe="")
        url = (
            f"{base_url}/openai/deployments/{deployment}/chat/completions"
            f"?api-version={urllib.parse.quote(config.api_version)}"
        )
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        response = _request_json(
            url,
            headers={"Content-Type": "application/json", "api-key": api_key},
            payload=payload,
            timeout_seconds=config.timeout_seconds,
        )
        content = response["choices"][0]["message"]["content"]
        usage = response.get("usage", {})
        return (
            str(content),
            _usage(
                config,
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
            ),
            response,
        )
    if config.provider == ProviderKind.openai:
        base_url = (config.base_url or "https://api.openai.com").rstrip("/")
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        response = _request_json(
            f"{base_url}/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            payload=payload,
            timeout_seconds=config.timeout_seconds,
        )
        content = response["choices"][0]["message"]["content"]
        usage = response.get("usage", {})
        return (
            str(content),
            _usage(
                config,
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
            ),
            response,
        )
    if config.provider == ProviderKind.anthropic:
        base_url = (config.base_url or "https://api.anthropic.com").rstrip("/")
        payload = {
            "model": config.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": config.temperature,
            "max_tokens": config.max_output_tokens,
        }
        response = _request_json(
            f"{base_url}/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            payload=payload,
            timeout_seconds=config.timeout_seconds,
        )
        content = "".join(
            str(block.get("text", ""))
            for block in response.get("content", [])
            if block.get("type") == "text"
        )
        usage = response.get("usage", {})
        return (
            content,
            _usage(
                config,
                int(usage.get("input_tokens", 0)),
                int(usage.get("output_tokens", 0)),
            ),
            response,
        )
    raise ValueError(f"unsupported online provider: {config.provider}")


def complete_raw(
    config: ProviderConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    output_dir: Path,
    budget: Optional[BudgetLedger] = None,
) -> tuple[str, RawCompletionRecord]:
    """Complete one bounded request and retain a hash-bound provider record."""

    _ensure_call_capacity(config, system_prompt, user_prompt, budget)
    request_payload = {"system": system_prompt, "user": user_prompt}
    request_encoded = _json_bytes(request_payload)
    if config.provider == ProviderKind.replay:
        replay_path = Path(str(config.replay_path))
        raw_response = json.loads(replay_path.read_text(encoding="utf-8"))
        content = json.dumps(raw_response)
        usage = UsageRecord()
    else:
        content, usage, raw_response = _online_call(config, system_prompt, user_prompt)
    if budget is not None:
        budget.record(usage)
    output_dir.mkdir(parents=True, exist_ok=False)
    response_path = output_dir / "provider_response.json"
    response_path.write_text(
        json.dumps(raw_response, indent=2) + "\n",
        encoding="utf-8",
    )
    record = RawCompletionRecord(
        provider=config.provider.value,
        model=config.model,
        request_sha256=hashlib.sha256(request_encoded).hexdigest(),
        response_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        usage=usage,
        raw_response_path=response_path.name,
    )
    record.finalize_hash()
    (output_dir / "call_record.json").write_text(
        record.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return content, record


def propose(
    config: ProviderConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    output_dir: Path,
    budget: Optional[BudgetLedger] = None,
) -> LLMCallRecord:
    _ensure_call_capacity(config, system_prompt, user_prompt, budget)
    request_payload = {"system": system_prompt, "user": user_prompt}
    request_encoded = _json_bytes(request_payload)
    if config.provider == ProviderKind.replay:
        replay_path = Path(str(config.replay_path))
        response = json.loads(replay_path.read_text(encoding="utf-8"))
        content = json.dumps(response)
        usage = UsageRecord()
        raw_response = response
    else:
        content, usage, raw_response = _online_call(config, system_prompt, user_prompt)
    if budget is not None:
        budget.record(usage)
    parsed = _extract_json_object(content)
    proposals, malformed_proposals = _parse_proposals(parsed)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "provider_response.json"
    raw_path.write_text(
        json.dumps(raw_response, indent=2) + "\n",
        encoding="utf-8",
    )
    response_encoded = _json_bytes(parsed)
    proposal_path = output_dir / "proposal_response.json"
    proposal_path.write_text(
        json.dumps(parsed, indent=2) + "\n",
        encoding="utf-8",
    )
    record = LLMCallRecord(
        provider=config.provider.value,
        model=config.model,
        request_sha256=hashlib.sha256(request_encoded).hexdigest(),
        response_sha256=hashlib.sha256(response_encoded).hexdigest(),
        usage=usage,
        proposals=proposals,
        malformed_proposals=malformed_proposals,
        raw_response_path=proposal_path.name,
    )
    record.finalize_hash()
    return record
