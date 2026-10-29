"""A local HTTP probe must not masquerade as a completed channel."""

import subprocess
from urllib.request import urlopen

from executors import fox_kitten_real


def test_http_probe_uses_its_own_ephemeral_loopback_listener(monkeypatch, tmp_path):
    monkeypatch.setattr(
        fox_kitten_real.tempfile, "mktemp",
        lambda **_kwargs: str(tmp_path / "http-probe.txt"),
    )
    observed_urls = []

    def probe(command, **_kwargs):
        url = command[-1]
        observed_urls.append(url)
        with urlopen(url, timeout=2) as response:
            assert response.status == 200
            assert response.read() == b"STICKS local protocol probe\n"
        return subprocess.CompletedProcess(command, 0, "HTTP Status: 200", "")

    monkeypatch.setattr(fox_kitten_real.subprocess, "run", probe)

    success, _message, error, _artifacts = fox_kitten_real.execute_t1071_001_inspired(
        "0.outer_space", "0.outer_space"
    )

    assert success
    assert error == ""
    assert len(observed_urls) == 1
    assert observed_urls[0].startswith("http://127.0.0.1:")
    assert observed_urls[0] != "http://127.0.0.1"


def test_failed_http_probe_is_not_a_success(monkeypatch, tmp_path):
    monkeypatch.setattr(
        fox_kitten_real.tempfile,
        "mktemp",
        lambda **_kwargs: str(tmp_path / "http-probe.txt"),
    )
    monkeypatch.setattr(
        fox_kitten_real.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["curl"], 7, "HTTP Status: 000", "Connection refused"
        ),
    )

    success, _message, error, artifacts = fox_kitten_real.execute_t1071_001_inspired(
        "0.outer_space", "0.outer_space"
    )

    assert not success
    assert "Connection refused" in error
    assert artifacts == [str(tmp_path / "http-probe.txt")]


def test_timed_out_http_probe_is_not_a_success(monkeypatch, tmp_path):
    monkeypatch.setattr(
        fox_kitten_real.tempfile,
        "mktemp",
        lambda **_kwargs: str(tmp_path / "http-probe.txt"),
    )

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["curl"], 5)

    monkeypatch.setattr(fox_kitten_real.subprocess, "run", timeout)

    success, _message, error, artifacts = fox_kitten_real.execute_t1071_001_inspired(
        "0.outer_space", "0.outer_space"
    )

    assert not success
    assert "timed out" in error
    assert artifacts == [str(tmp_path / "http-probe.txt")]


def test_completed_http_probe_remains_a_simulation(monkeypatch, tmp_path):
    monkeypatch.setattr(
        fox_kitten_real.tempfile,
        "mktemp",
        lambda **_kwargs: str(tmp_path / "http-probe.txt"),
    )
    monkeypatch.setattr(
        fox_kitten_real.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["curl"], 0, "HTTP Status: 200", ""
        ),
    )

    success, _message, error, artifacts = fox_kitten_real.execute_t1071_001_inspired(
        "0.outer_space", "0.outer_space"
    )

    assert success
    assert error == ""
    assert artifacts == [str(tmp_path / "http-probe.txt")]
