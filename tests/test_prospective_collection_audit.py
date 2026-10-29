"""Fail-closed checks for prospectively collected proposal cells."""

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import audit_prospective_collection as audit  # noqa: E402
import analyze_controlled_comparison as analysis  # noqa: E402
from audit_prospective_collection import audit_cache_cells, audit_manifest, audit_semantic_replay  # noqa: E402
from collect_controlled_comparison import (  # noqa: E402
    collection_budget_sha,
    collection_oracle_revision,
    load_campaign_fixture,
)
from evaluation.collection_lock import CollectionLock  # noqa: E402
from evaluation.comparison_runner import (  # noqa: E402
    GenerationReceipt,
    StepObservation,
    compute_arm_metrics,
    observe_step,
)
from evaluation.controlled_comparison import ArmId, NeutralProposalRecord  # noqa: E402


def _lock() -> CollectionLock:
    return CollectionLock(
        experiment_id="future-test",
        model="local-model",
        ollama_model_digest="a" * 64,
        temperature=0.7,
        thinking_mode=False,
        max_output_tokens=128,
        timeout_seconds=20,
        retry_limit=2,
        campaigns=["C0010"],
        seeds=[1],
        shuffle_seed=7,
        source_sha256={},
    )


def _observation(*, arm_id: str = "prior_work_style", with_receipt: bool = True) -> StepObservation:
    raw_output = '{"template_id":"example"}'
    proposal = NeutralProposalRecord(
        proposal_id="proposal-1",
        experiment_id="future-test",
        campaign_id="C0010",
        step_id="s1",
        arm_id=ArmId(arm_id),
        seed=1,
        technique_id="T0001",
        execution_domain="linux",
        template_id="example",
        proposal_budget_sha256="b" * 64,
        raw_output_sha256=hashlib.sha256(raw_output.encode()).hexdigest(),
    )
    proposal.finalize_hash()
    generation = GenerationReceipt(
        request_body=json.dumps(
            {
                "model": "local-model",
                "stream": False,
                "think": False,
                "options": {"seed": 1, "temperature": 0.7, "num_predict": 128},
                "messages": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "user"},
                ],
            }
        ),
        response_body=json.dumps({"message": {"content": raw_output}}),
        raw_output_sha256=hashlib.sha256(raw_output.encode()).hexdigest(),
        recorded_at="2026-10-22T00:00:00+00:00",
        elapsed_seconds=0.1,
        attempt_count=1,
    )
    return StepObservation(
        campaign_id="C0010",
        arm_id=arm_id,
        seed=1,
        step_id="s1",
        emitted=True,
        abstained=False,
        template_id=proposal.template_id,
        proposal_sha256=proposal.content_sha256,
        proposal_record=proposal,
        generation=generation if with_receipt else None,
    )


def _expected() -> dict[str, tuple[str, str, int, str]]:
    return {"C0010__prior_work_style__seed1__s1.json": ("C0010", "prior_work_style", 1, "s1")}


def test_complete_cell_with_raw_receipt_passes(tmp_path: Path):
    (tmp_path / next(iter(_expected()))).write_text(_observation().model_dump_json())
    assert len(audit_cache_cells(tmp_path, _expected(), _lock())) == 1


def test_schema_two_requires_request_sampling_option(tmp_path: Path):
    lock = _lock().model_copy(update={
        "schema_version": 2, "top_p": 0.9, "runtime_id": "ollama:test",
    })
    observation = _observation()
    destination = tmp_path / next(iter(_expected()))
    destination.write_text(observation.model_dump_json())
    with pytest.raises(ValueError, match="top_p differs"):
        audit_cache_cells(tmp_path, _expected(), lock)
    request = json.loads(observation.generation.request_body)
    request["options"]["top_p"] = 0.9
    observation.generation.request_body = json.dumps(request)
    destination.write_text(observation.model_dump_json())
    assert len(audit_cache_cells(tmp_path, _expected(), lock)) == 1


def test_missing_or_extra_cell_fails(tmp_path: Path):
    with pytest.raises(ValueError, match="1 missing"):
        audit_cache_cells(tmp_path, _expected(), _lock())
    (tmp_path / "unexpected.json").write_text("{}")
    with pytest.raises(ValueError, match="1 missing, 1 unexpected"):
        audit_cache_cells(tmp_path, _expected(), _lock())


def test_old_cache_without_raw_receipt_fails(tmp_path: Path):
    (tmp_path / next(iter(_expected()))).write_text(_observation(with_receipt=False).model_dump_json())
    with pytest.raises(ValueError, match="missing raw generation receipt"):
        audit_cache_cells(tmp_path, _expected(), _lock())


def test_cache_identity_and_request_must_match_lock(tmp_path: Path):
    filename = next(iter(_expected()))
    observation = _observation()
    changed_identity = observation.model_copy(deep=True)
    changed_identity.step_id = "s2"
    changed_identity.proposal_record.step_id = "s2"
    changed_identity.proposal_record.finalize_hash()
    changed_identity.proposal_sha256 = changed_identity.proposal_record.content_sha256
    (tmp_path / filename).write_text(changed_identity.model_dump_json())
    with pytest.raises(ValueError, match="cached identity differs"):
        audit_cache_cells(tmp_path, _expected(), _lock())
    (tmp_path / filename).write_text(observation.model_dump_json())
    changed_lock = _lock().model_copy(update={"temperature": 0.2})
    with pytest.raises(ValueError, match="temperature differs"):
        audit_cache_cells(tmp_path, _expected(), changed_lock)


def test_altered_raw_output_hash_fails_without_echoing_model_text(tmp_path: Path):
    filename = next(iter(_expected()))
    payload = _observation().model_dump()
    payload["generation"]["raw_output_sha256"] = "0" * 64
    (tmp_path / filename).write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="invalid cached cell") as error:
        audit_cache_cells(tmp_path, _expected(), _lock())
    assert "template_id" not in str(error.value)


def test_manifest_must_declare_proposal_scope(tmp_path: Path):
    lock_path = tmp_path / "collection-lock.json"
    lock_path.write_text(_lock().model_dump_json())
    (tmp_path / "manifest.json").write_text(json.dumps({"experiment_id": "future-test"}))
    with pytest.raises(ValueError, match="manifest study_scope differs"):
        audit_manifest(tmp_path, _lock(), 1)


def test_complete_frozen_collection_passes_preflight(tmp_path: Path, monkeypatch):
    lock = _lock()
    directory = tmp_path / "release/experiments/controlled_comparison/future-test"
    cache_dir = directory / "cache"
    cache_dir.mkdir(parents=True)
    lock_bytes = lock.model_dump_json().encode()
    (directory / "collection-lock.json").write_bytes(lock_bytes)
    observations = []
    for arm in audit.COMPARABLE_ARMS:
        observation = _observation(arm_id=arm.value)
        observations.append(observation)
        (cache_dir / f"C0010__{arm.value}__seed1__s1.json").write_text(observation.model_dump_json())
    manifest = {
        "experiment_id": lock.experiment_id,
        "study_scope": "proposal_only",
        "arm_ids": [arm.value for arm in audit.COMPARABLE_ARMS],
        "model": lock.model,
        "ollama_model_digest": lock.ollama_model_digest,
        "temperature": lock.temperature,
        "thinking_mode": lock.thinking_mode,
        "campaigns": lock.campaigns,
        "seeds": lock.seeds,
        "shuffle_seed": lock.shuffle_seed,
        "cells": 3,
        "collection_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    metrics = {
        arm.value: compute_arm_metrics(observations, arm).model_dump()
        for arm in audit.COMPARABLE_ARMS
    }
    (directory / "metrics.json").write_text(json.dumps(metrics))
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(audit, "verify_collection_sources", lambda project_root, run_dir: lock)
    monkeypatch.setattr(audit, "audit_semantic_replay", lambda observations, frozen_lock: None)
    monkeypatch.setattr(
        audit,
        "load_campaign_fixture",
        lambda campaign: SimpleNamespace(steps=[SimpleNamespace(step_id="s1")]),
    )
    assert audit.audit_collection("future-test") == 3


def _replay_observation() -> tuple[StepObservation, CollectionLock]:
    lock = _lock().model_copy(update={
        "source_sha256": {
            "src/concretization/verifier.py": "b" * 64,
            "src/evaluation/controlled_comparison.py": "c" * 64,
        }
    })
    fixture = load_campaign_fixture("C0010")
    step = fixture.steps[0]
    template_id = next(
        template.template_id
        for template in fixture.templates
        if step.technique_id in template.technique_ids
    )
    raw_output = json.dumps({"template_id": template_id, "bindings": {}})
    messages = []

    def complete(system_prompt: str, user_prompt: str) -> str:
        messages.extend([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        return raw_output

    observation = observe_step(
        ArmId.prior_work_style,
        step,
        fixture,
        1,
        experiment_id=lock.experiment_id,
        budget_sha=collection_budget_sha(lock),
        oracle_revision=collection_oracle_revision(lock),
        complete=complete,
        retain_proposal=True,
    )
    request = json.loads(_observation().generation.request_body)
    request["messages"] = messages
    observation.generation = GenerationReceipt(
        request_body=json.dumps(request),
        response_body=json.dumps({"message": {"content": raw_output}}),
        raw_output_sha256=hashlib.sha256(raw_output.encode()).hexdigest(),
        recorded_at="2026-10-22T00:00:00+00:00",
        elapsed_seconds=0.1,
        attempt_count=1,
    )
    return observation, lock


def test_semantic_replay_matches_real_planner_decision():
    observation, lock = _replay_observation()
    audit_semantic_replay([observation], lock)


def test_semantic_replay_rejects_tampered_decision_and_prompt():
    observation, lock = _replay_observation()
    changed_decision = observation.model_copy(deep=True)
    changed_decision.oracle_admitted = not observation.oracle_admitted
    with pytest.raises(ValueError, match="cached decision differs"):
        audit_semantic_replay([changed_decision], lock)

    changed_prompt = observation.model_copy(deep=True)
    request = json.loads(changed_prompt.generation.request_body)
    request["messages"][1]["content"] = "tampered"
    changed_prompt.generation.request_body = json.dumps(request)
    with pytest.raises(ValueError, match="generated prompt differs"):
        audit_semantic_replay([changed_prompt], lock)


def test_analysis_refuses_collection_before_reading_cache(monkeypatch):
    monkeypatch.setattr(analysis, "parse_args", lambda: SimpleNamespace(experiment_id="future-test"))

    def reject_collection(experiment_id: str) -> int:
        assert experiment_id == "future-test"
        raise ValueError("missing raw generation receipt")

    def forbid_cache_read(experiment_dir: Path) -> list[dict]:
        pytest.fail(f"analysis read unaudited cache: {experiment_dir}")

    monkeypatch.setattr(analysis, "audit_collection", reject_collection)
    monkeypatch.setattr(analysis, "load_observations", forbid_cache_read)
    with pytest.raises(ValueError, match="missing raw generation receipt"):
        analysis.main()
