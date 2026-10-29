"""Profile weakness declarations must not create undeclared lab accounts."""

from pathlib import Path

import pytest

from src.apply_sut_profile import apply_weak_credentials, apply_weaknesses_to_host


def _apply(weakness, users, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "src.apply_sut_profile.apply_weak_credentials",
        lambda *_args: calls.append(weakness) or True,
    )
    results = {"weaknesses_applied": [], "errors": []}
    apply_weaknesses_to_host(
        "192.168.56.30", "target-base", [weakness], "qemu",
        "target-linux-1", Path("/unused"), results, set(users),
    )
    return results, calls


def test_implicit_weakness_uses_only_declared_account(monkeypatch):
    results, calls = _apply(
        {"type": "weak_ssh_password"}, {"rayuser"}, monkeypatch
    )
    assert results == {
        "weaknesses_applied": ["weak_ssh_password"], "errors": [],
    }
    assert calls == []


@pytest.mark.parametrize("users", (set(), {"alice", "bob"}))
def test_implicit_weakness_rejects_missing_or_ambiguous_accounts(
    monkeypatch, users
):
    results, calls = _apply(
        {"type": "weak_credentials"}, users, monkeypatch
    )
    assert results["weaknesses_applied"] == []
    assert "unambiguous declared user" in results["errors"][0]
    assert calls == []


def test_explicit_existing_account_does_not_get_recreated(monkeypatch):
    results, calls = _apply(
        {"type": "weak_credentials", "username": "rayuser"},
        {"rayuser"}, monkeypatch,
    )
    assert results["weaknesses_applied"] == ["weak_credentials"]
    assert calls == []


def test_credential_provisioning_never_invents_a_password(monkeypatch):
    monkeypatch.setattr(
        "src.apply_sut_profile.execute_ssh_command",
        lambda *_args, **_kwargs: pytest.fail("SSH must not run"),
    )
    with pytest.raises(ValueError, match="explicit username and password"):
        apply_weak_credentials(
            "192.168.56.30", {"username": "rayuser"}, "qemu",
            "target-linux-1", Path("/unused"),
        )
