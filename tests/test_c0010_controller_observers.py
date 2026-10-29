"""C0010 controller observations cannot be promoted from executor success."""

from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path

import pytest

from runners import c0010_controller_observers as controller_observers
from runners.capability_authority import (
    acquire_registered_observation,
    verify_registered_observation,
)
from runners.capability_facts import FactScope
from scripts.probe_c0010_controller import _EXPECTED_FILES


def _scope() -> FactScope:
    return FactScope(
        run_id="run-synthetic",
        environment_id="lab-run-synthetic",
        epoch="run-synthetic",
        locus="controller",
        host_id="controller",
        principal=str(os.geteuid()),
    )


def _request() -> controller_observers.C0010ControllerRequest:
    return controller_observers.controller_request(
        "c0010-payload",
        _scope(),
        "challenge-synthetic",
        2,
    )


def _stage_payload(root: Path, content: bytes) -> None:
    target = root / "data/artifacts/staging/benign_payload.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(content)


def test_observer_grants_only_measured_controller_product(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controller_observers, "_PROJECT_ROOT", tmp_path)
    _stage_payload(
        tmp_path,
        b"#!/bin/sh\necho 'STICKS controlled payload artifact'\n",
    )

    observation = controller_observers.observe_c0010_controller(_request())

    assert observation.passed
    assert observation.established_facts == ("controller:payload_staged",)
    assert observation.producer_occurrence == 2
    assert observation.details["file_count"] == 1
    assert observation.content_sha256 is not None


@pytest.mark.parametrize("content", [None, b"wrong bytes"])
def test_observer_fails_without_measured_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: bytes | None,
) -> None:
    monkeypatch.setattr(controller_observers, "_PROJECT_ROOT", tmp_path)
    if content is not None:
        _stage_payload(tmp_path, content)

    observation = controller_observers.observe_c0010_controller(_request())

    assert not observation.passed
    assert observation.established_facts == ()


def test_probe_and_dispatch_allowlists_remain_in_sync() -> None:
    assert set(controller_observers._PREDICATES) == set(_EXPECTED_FILES)
    for predicate_id, specification in controller_observers._PREDICATES.items():
        assert specification.paths == frozenset(_EXPECTED_FILES[predicate_id])


def test_controller_spec_change_requires_new_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = json.loads(controller_observers._SPEC_PATH.read_text())
    document["predicates"][0]["files"][0]["utf8"] = "altered"
    changed_spec = tmp_path / "c0010_controller.json"
    changed_spec.write_text(json.dumps(document))
    monkeypatch.setattr(controller_observers, "_SPEC_PATH", changed_spec)

    with pytest.raises(ValueError, match="reviewed bytes"):
        controller_observers._load_predicates()


def test_wrong_probe_identity_reports_failed_condition_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_reply = {
        "schema": "c0010-controller-probe/v1",
        "predicate_id": "payload-staged",
        "run_id": "wrong-run",
        "nonce": "wrong-nonce",
        "hostname": "wrong-host",
        "uid": os.geteuid(),
        "passed": True,
        "content_sha256": "0" * 64,
        "file_sha256": [
            {"path": "data/artifacts/staging/benign_payload.bin", "sha256": "0" * 64}
        ],
    }
    monkeypatch.setattr(
        controller_observers.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            ["probe"], 0, json.dumps(probe_reply), ""
        ),
    )

    observed = controller_observers.observe_c0010_controller(_request())

    assert not observed.passed
    assert observed.established_facts == ()
    assert set(observed.details["failed_checks"].split(",")) == {
        "run",
        "nonce",
        "hostname",
        "content_digest",
    }
    assert "wrong-run" not in str(observed.details)


def test_scope_cannot_impersonate_guest() -> None:
    invalid_scope = _scope().model_copy(update={"locus": "target"})

    with pytest.raises(ValueError, match="live controller scope"):
        controller_observers.controller_request(
            "c0010-payload",
            invalid_scope,
            "challenge-synthetic",
            2,
        )


@pytest.mark.parametrize(
    ("authority_id", "wrong_occurrence"),
    [("c0010-payload", 3), ("c0010-page", 2), ("c0010-tool", 8)],
)
def test_predicate_cannot_be_attributed_to_another_occurrence(
    authority_id: str,
    wrong_occurrence: int,
) -> None:
    with pytest.raises(ValueError, match="campaign occurrence"):
        controller_observers.controller_request(
            authority_id,
            _scope(),
            "challenge-synthetic",
            wrong_occurrence,
        )


def test_registered_dispatch_binds_predicate_and_retained_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "workspace"
    source.mkdir()
    run_root = tmp_path / "run"
    run_root.mkdir()
    monkeypatch.setattr(controller_observers, "_PROJECT_ROOT", source)
    _stage_payload(
        source,
        b"#!/bin/sh\necho 'STICKS controlled payload artifact'\n",
    )
    request = _request()

    reference = acquire_registered_observation(
        "c0010-payload",
        request,
        run_root=run_root,
    )
    observed = verify_registered_observation(
        reference,
        run_root=run_root,
        expected_scope=request.scope,
        expected_predicate="payload-staged",
    )

    assert observed.passed
    assert observed.established_facts == ("controller:payload_staged",)
    with pytest.raises(ValueError, match="Request predicate"):
        acquire_registered_observation("c0010-tool", request, run_root=run_root)
