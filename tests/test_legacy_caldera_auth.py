from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "measurement/sut/scripts"


def load_script(name: str):
    pytest.importorskip("requests", reason="legacy HTTP integration dependency")
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SessionStub:
    def __init__(self) -> None:
        self.submitted_password: str | None = None

    def get(self, url: str) -> SimpleNamespace:
        return SimpleNamespace(status_code=200)

    def post(self, url: str, *, data: dict, allow_redirects: bool) -> SimpleNamespace:
        self.submitted_password = data["password"]
        return SimpleNamespace(status_code=200, headers={})


@pytest.mark.parametrize("script_name", ["run_campaign", "run_finite"])
def test_legacy_login_requires_explicit_password(
    script_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = load_script(script_name)
    monkeypatch.delenv("CALDERA_PASSWORD", raising=False)
    session = SessionStub()
    monkeypatch.setattr(script.requests, "Session", lambda: session)

    with pytest.raises(KeyError, match="CALDERA_PASSWORD"):
        if script_name == "run_campaign":
            script.login(session)
        else:
            script.login()

    assert session.submitted_password is None


@pytest.mark.parametrize("script_name", ["run_campaign", "run_finite"])
def test_legacy_login_uses_supplied_password(
    script_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = load_script(script_name)
    monkeypatch.setenv("CALDERA_PASSWORD", "fixture-password")
    session = SessionStub()
    monkeypatch.setattr(script.requests, "Session", lambda: session)

    if script_name == "run_campaign":
        assert script.login(session)
    else:
        assert script.login() is session

    assert session.submitted_password == "fixture-password"
