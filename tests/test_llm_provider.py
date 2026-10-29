from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization import provider as provider_module  # noqa: E402
from concretization.provider import (  # noqa: E402
    ArtifactConfig,
    BudgetConfig,
    BudgetLedger,
    ProviderConfig,
    ProviderKind,
    UsageRecord,
    complete_raw,
)


class _FakeResponse:
    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b"[]"


def test_config_rejects_literal_api_key() -> None:
    payload = {
        "llm": {
            "provider": "openai",
            "model": "test",
            "api_key_env": "OPENAI_API_KEY",
            "api_key": "must-not-be-supported",
        }
    }
    with pytest.raises(ValidationError):
        ArtifactConfig.model_validate(payload)


def test_budget_fails_before_silent_overspend() -> None:
    ledger = BudgetLedger(
        BudgetConfig(
            max_requests=1,
            max_prompt_tokens=10,
            max_completion_tokens=10,
            max_estimated_usd=1.0,
        )
    )
    ledger.record(UsageRecord(prompt_tokens=5, completion_tokens=5))
    with pytest.raises(RuntimeError, match="request budget"):
        ledger.record(UsageRecord(prompt_tokens=1, completion_tokens=1))


def test_example_configuration_contains_no_credential() -> None:
    payload = json.loads((PROJECT_ROOT / "config.example.json").read_text(encoding="utf-8"))
    assert "api_key" not in payload["llm"]
    assert payload["llm"]["api_key_env"] == "AZURE_OPENAI_API_KEY"


def test_online_provider_requires_explicit_price_configuration() -> None:
    with pytest.raises(ValidationError, match="token prices"):
        ProviderConfig(
            provider=ProviderKind.openai,
            model="test",
            api_key_env="OPENAI_API_KEY",
        )


def test_online_budget_is_checked_before_any_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = ProviderConfig(
        provider=ProviderKind.openai,
        model="test",
        api_key_env="OPENAI_API_KEY",
        max_output_tokens=10,
        budget=BudgetConfig(
            max_requests=1,
            max_prompt_tokens=1,
            max_completion_tokens=10,
            max_estimated_usd=1.0,
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=1.0,
        ),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    called = False

    def fail_if_called(*args: object, **kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("provider call must not occur after preflight rejection")

    monkeypatch.setattr(provider_module, "_online_call", fail_if_called)

    with pytest.raises(RuntimeError, match="prompt-token budget"):
        complete_raw(
            config,
            system_prompt="system",
            user_prompt="user",
            output_dir=tmp_path / "call",
            budget=BudgetLedger(config.budget),
        )

    assert not called


def test_request_budget_blocks_before_reading_provider_response(tmp_path: Path) -> None:
    replay_path = tmp_path / "response.json"
    replay_path.write_text("{}", encoding="utf-8")
    config = ProviderConfig(
        provider=ProviderKind.replay,
        model="replay",
        api_key_env="UNUSED",
        replay_path=str(replay_path),
        budget=BudgetConfig(max_requests=1),
    )
    ledger = BudgetLedger(config.budget)
    complete_raw(
        config,
        system_prompt="system",
        user_prompt="user",
        output_dir=tmp_path / "first",
        budget=ledger,
    )
    replay_path.unlink()

    with pytest.raises(RuntimeError, match="request budget"):
        complete_raw(
            config,
            system_prompt="system",
            user_prompt="user",
            output_dir=tmp_path / "second",
            budget=ledger,
        )


def test_http_provider_rejects_non_object_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_module.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(),
    )

    with pytest.raises(ValueError, match="JSON object with string keys"):
        provider_module._request_json(
            "https://provider.invalid",
            headers={},
            payload={},
            timeout_seconds=1,
        )


def test_loopback_endpoint_does_not_require_token_prices():
    """A model served from this host bills nothing, so a zero price is valid."""
    config = ProviderConfig(
        provider=ProviderKind.openai,
        model="gpt-oss:20b",
        base_url="http://localhost:11434",
        api_key_env="OLLAMA_API_KEY",
        budget=BudgetConfig(input_usd_per_million_tokens=0.0, output_usd_per_million_tokens=0.0),
    )
    assert config.base_url == "http://localhost:11434"


def test_remote_endpoint_still_requires_token_prices():
    """A metered provider must price its tokens so the budget can be enforced."""
    with pytest.raises(ValidationError):
        ProviderConfig(
            provider=ProviderKind.openai,
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            budget=BudgetConfig(input_usd_per_million_tokens=0.0, output_usd_per_million_tokens=0.0),
        )
