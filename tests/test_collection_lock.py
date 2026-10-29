"""Prospective comparison caches cannot mix different experimental conditions."""

from __future__ import annotations

import io
import hashlib
import json
import sys
import urllib.error
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import collect_controlled_comparison as collector  # noqa: E402
from collect_controlled_comparison import (  # noqa: E402
    ensure_thinking_mode_supported,
    ollama_completion,
    ollama_model_digest,
)
from evaluation.collection_lock import (  # noqa: E402
    EXECUTION_INPUT_DIRECTORIES,
    build_collection_lock,
    prepare_collection_directory,
    verify_frozen_collection_sources,
    verify_collection_sources,
)
from evaluation.comparison_runner import GenerationReceipt, StepObservation  # noqa: E402
from evaluation.controlled_comparison import NeutralProposalRecord  # noqa: E402


def _lock(**changes):
    parameters = {
        "experiment_id": "prospective-comparison",
        "model": "qwen2.5-coder:14b",
        "ollama_model_digest": "a" * 64,
        "temperature": 0.7,
        "thinking_mode": False,
        "max_output_tokens": 512,
        "timeout_seconds": 300,
        "retry_limit": 3,
        "campaigns": ["C0010"],
        "seeds": [1, 2, 3, 4, 5],
        "shuffle_seed": 20261019,
    }
    parameters.update(changes)
    return build_collection_lock(PROJECT_ROOT, **parameters)


def test_identical_lock_can_resume_but_changed_conditions_cannot(tmp_path):
    directory = tmp_path / "prospective-comparison"
    original = _lock()
    lock_path = prepare_collection_directory(directory, original)
    assert prepare_collection_directory(directory, original) == lock_path
    assert json.loads(lock_path.read_text())["ollama_model_digest"] == "a" * 64
    with pytest.raises(ValueError, match="differ from frozen lock"):
        prepare_collection_directory(directory, _lock(temperature=0.2))
    with pytest.raises(ValueError, match="differ from frozen lock"):
        prepare_collection_directory(directory, _lock(ollama_model_digest="b" * 64))
    with pytest.raises(ValueError, match="differ from frozen lock"):
        prepare_collection_directory(directory, _lock(thinking_mode=True))
    assert prepare_collection_directory(directory, original) == lock_path


def test_runtime_metadata_is_versioned_and_cannot_change_on_resume(tmp_path):
    original = _lock(top_p=0.9, runtime_id="ollama:0.15.0")
    assert original.schema_version == 4
    prepare_collection_directory(tmp_path, original, project_root=PROJECT_ROOT)
    for changed in (
        _lock(top_p=0.8, runtime_id="ollama:0.15.0"),
        _lock(top_p=0.9, runtime_id="ollama:0.15.1"),
    ):
        with pytest.raises(ValueError, match="differ from frozen lock"):
            prepare_collection_directory(tmp_path, changed)


def test_partial_runtime_metadata_is_rejected():
    with pytest.raises(ValueError, match="requires explicit"):
        _lock(top_p=1.0)
    assert _lock().schema_version == 1


@pytest.mark.parametrize(
    "relative_path",
    [
        "scripts/probe_c0026_target.py",
        "data/runtime_contracts/c0026.json",
        "lab/vagrant/shared/target.sh",
        "requirements.lock",
    ],
)
def test_execution_input_drift_rejects_resume(tmp_path, relative_path):
    import shutil

    source = tmp_path / "source"
    source.mkdir()
    for directory in ("src", *EXECUTION_INPUT_DIRECTORIES):
        shutil.copytree(
            PROJECT_ROOT / directory,
            source / directory,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".vagrant", "__pycache__"),
        )
    for name in ("requirements.txt", "requirements.lock"):
        shutil.copyfile(PROJECT_ROOT / name, source / name)
    shutil.copytree(PROJECT_ROOT / "release/plans", source / "release/plans")
    parameters = _lock(top_p=0.9, runtime_id="ollama:test")
    # Rebuild using the copied tree so path additions are covered as well as bytes.
    from evaluation.collection_lock import CollectionLock

    lock_values = parameters.model_dump(
        exclude={"source_sha256", "source_tree_sha256", "schema_version"}
    )
    original = build_collection_lock(source, **lock_values)
    assert isinstance(original, CollectionLock)
    assert relative_path in original.source_sha256
    collection = tmp_path / "collection"
    prepare_collection_directory(collection, original, project_root=source)
    changed = source / relative_path
    changed.write_bytes(changed.read_bytes() + b"\n# changed\n")
    with pytest.raises(ValueError, match="source differs"):
        verify_collection_sources(source, collection)


def test_schema_two_keeps_legacy_source_population():
    original = _lock(top_p=0.9, runtime_id="ollama:test", schema_version=2)
    assert original.schema_version == 2
    assert "scripts/probe_c0026_target.py" not in original.source_sha256


def test_formal_manifest_and_grid_are_prepared_without_generation(tmp_path):
    from evaluation.controlled_comparison import ControlledComparisonManifest, RunLedger

    lock = _lock(top_p=0.9, runtime_id="ollama:test")
    collector.prepare_formal_comparison(tmp_path, lock)
    manifest = ControlledComparisonManifest.model_validate_json(
        (tmp_path / "comparison-manifest.json").read_text()
    )
    ledger_path = tmp_path / "comparison-ledger.json"
    ledger = RunLedger.model_validate_json(ledger_path.read_text())
    manifest.validate_collection_ready()
    ledger.validate_against(manifest)
    assert len(ledger.records) == 20
    assert all(record.status.value == "planned" for record in ledger.records)
    assert (
        collector.collection_budget_sha(lock)
        == manifest.arms[0].proposal_budget.comparison_sha256()
    )
    original_bytes = ledger_path.read_bytes()
    collector.prepare_formal_comparison(tmp_path, lock)
    assert ledger_path.read_bytes() == original_bytes
    with pytest.raises(ValueError, match="formal comparison differs"):
        collector.prepare_formal_comparison(
            tmp_path, _lock(top_p=0.8, runtime_id="ollama:test")
        )


def test_formal_budget_records_retries_after_first_attempt():
    lock = _lock(top_p=0.9, runtime_id="ollama:test", retry_limit=3)
    budget = collector.formal_generator_budget(lock)
    assert budget.max_retries_per_step == 2
    assert budget.max_proposal_calls_per_step == 1
    with pytest.raises(ValueError, match="schema 3"):
        collector.formal_generator_budget(_lock())


@pytest.mark.parametrize("top_p", [0, -0.1, 1.1, float("nan"), float("inf")])
def test_invalid_sampling_probability_is_rejected(top_p):
    with pytest.raises(ValueError):
        _lock(top_p=top_p, runtime_id="ollama:test")


def test_runtime_drift_stops_before_model_request(monkeypatch):
    from scripts import collect_controlled_comparison as collector

    monkeypatch.setattr(collector, "ollama_runtime_id", lambda: "ollama:changed")
    complete = collector.ollama_completion(
        "model", 0.2, 1, expected_runtime_id="ollama:frozen"
    )
    with pytest.raises(RuntimeError, match="runtime changed"):
        complete("system", "user")


def test_legacy_cache_without_lock_is_rejected_without_modification(tmp_path):
    directory = tmp_path / "historical"
    cache = directory / "cache"
    cache.mkdir(parents=True)
    historical_record = cache / "cell.json"
    historical_record.write_text("historical evidence\n")

    with pytest.raises(FileExistsError, match="no frozen lock"):
        prepare_collection_directory(directory, _lock())
    assert historical_record.read_text() == "historical evidence\n"
    assert not (directory / "collection-lock.json").exists()


def test_analysis_requires_exact_frozen_source(tmp_path):
    directory = tmp_path / "prospective-comparison"
    original = _lock()
    lock_path = prepare_collection_directory(directory, original)
    assert verify_collection_sources(PROJECT_ROOT, directory) == original

    changed = original.model_copy(
        update={
            "source_sha256": {
                **original.source_sha256,
                "scripts/analyze_controlled_comparison.py": "0" * 64,
            }
        }
    )
    lock_path.write_text(changed.model_dump_json())
    with pytest.raises(ValueError, match="source differs from frozen collection"):
        verify_collection_sources(PROJECT_ROOT, directory)

    lock_path.unlink()
    with pytest.raises(ValueError, match="no frozen source lock"):
        verify_collection_sources(PROJECT_ROOT, directory)


def test_schema_four_seals_and_verifies_the_frozen_source_tree(tmp_path):
    original = _lock(top_p=0.9, runtime_id="ollama:test")
    assert original.schema_version == 4
    prepare_collection_directory(tmp_path, original, project_root=PROJECT_ROOT)
    assert verify_frozen_collection_sources(tmp_path, original).is_file()

    frozen_file = tmp_path / "frozen-source" / "src/evaluation/comparison_runner.py"
    frozen_file.write_bytes(frozen_file.read_bytes() + b"\n# tampered\n")
    with pytest.raises(ValueError, match="frozen source differs"):
        verify_frozen_collection_sources(tmp_path, original)


def test_schema_four_analysis_requires_the_sealed_source_tree(tmp_path):
    original = _lock(top_p=0.9, runtime_id="ollama:test")
    prepare_collection_directory(tmp_path, original, project_root=PROJECT_ROOT)
    (tmp_path / "frozen-source-manifest.json").unlink()
    with pytest.raises(ValueError, match="no frozen source snapshot"):
        verify_collection_sources(PROJECT_ROOT, tmp_path)


def test_schema_four_requires_an_explicit_source_project_root(tmp_path):
    with pytest.raises(ValueError, match="requires the source project root"):
        prepare_collection_directory(
            tmp_path, _lock(top_p=0.9, runtime_id="ollama:test")
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"experiment_id": "../outside"},
        {"campaigns": ["../C0010"]},
        {"seeds": [1, 2, 3, 4]},
        {"ollama_model_digest": "not-a-digest"},
    ],
)
def test_unsafe_or_incomplete_inputs_cannot_start_collection(changes):
    with pytest.raises(ValueError):
        _lock(**changes)


def test_model_digest_is_read_from_local_ollama_tags(monkeypatch):
    response = io.BytesIO(
        json.dumps(
            {"models": [{"name": "qwen2.5-coder:14b", "digest": "a" * 64}]}
        ).encode()
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: response)
    assert ollama_model_digest("qwen2.5-coder:14b") == "a" * 64


def test_thinking_mode_must_be_supported_by_the_model(monkeypatch):
    response = io.BytesIO(json.dumps({"thinking": {"values": [False, True]}}).encode())
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: response)
    ensure_thinking_mode_supported("qwen3.6:latest", False)

    response = io.BytesIO(json.dumps({"thinking": {"values": ["low"]}}).encode())
    with pytest.raises(ValueError, match="does not support thinking mode"):
        ensure_thinking_mode_supported("gpt-oss:20b", False)


def test_completion_sends_the_frozen_thinking_mode(monkeypatch):
    request_bodies = []

    def respond(request, timeout):
        request_bodies.append(json.loads(request.data))
        return io.BytesIO(b'{"message": {"content": "{}"}}')

    monkeypatch.setattr("urllib.request.urlopen", respond)
    complete = ollama_completion("qwen3.6:latest", 0.7, 1, thinking_mode=False)
    assert complete("system", "user") == "{}"
    assert request_bodies[0]["think"] is False
    assert request_bodies[0]["options"]["top_p"] == 1.0


def test_completion_receipt_keeps_exact_request_and_response(monkeypatch):
    response_body = b'{"message":{"content":"{\\"ok\\":true}"},"eval_count":12}'
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request, timeout: io.BytesIO(response_body)
    )
    receipts = []
    complete = ollama_completion(
        "qwen3.6:latest", 0.7, 1, thinking_mode=False, receipt_sink=receipts.append
    )
    assert complete("system", "user") == '{"ok":true}'
    assert len(receipts) == 1
    assert receipts[0].response_body == response_body.decode("utf-8")
    assert receipts[0].raw_output_sha256 == hashlib.sha256(b'{"ok":true}').hexdigest()
    assert json.loads(receipts[0].request_body)["messages"][1]["content"] == "user"
    assert receipts[0].attempt_count == 1


def test_generation_receipt_rejects_changed_raw_output():
    receipt = GenerationReceipt(
        request_body='{"model":"test"}',
        response_body='{"message":{"content":"first"}}',
        raw_output_sha256=hashlib.sha256(b"first").hexdigest(),
        recorded_at="2026-10-19T00:00:00+00:00",
        elapsed_seconds=0.1,
        attempt_count=1,
    )
    altered = receipt.model_dump()
    altered["response_body"] = '{"message":{"content":"second"}}'
    with pytest.raises(ValueError, match="raw output hash mismatch"):
        GenerationReceipt.model_validate(altered)


def test_model_change_stops_before_proposal_request(monkeypatch):
    monkeypatch.setattr(
        "collect_controlled_comparison.ollama_model_digest", lambda model: "b" * 64
    )
    complete = ollama_completion("qwen2.5-coder:14b", 0.7, 1, expected_digest="a" * 64)
    with pytest.raises(RuntimeError, match="model artifact changed"):
        complete("system", "user")


def test_authentication_failure_is_not_retried(monkeypatch):
    attempts = []

    def reject(request, timeout):
        attempts.append(request)
        raise urllib.error.HTTPError(request.full_url, 401, "unauthorized", None, None)

    monkeypatch.setattr("urllib.request.urlopen", reject)
    complete = ollama_completion("qwen2.5-coder:14b", 0.7, 1)
    with pytest.raises(urllib.error.HTTPError) as failure:
        complete("system", "user")
    assert failure.value.code == 401
    assert len(attempts) == 1


def test_transient_http_error_retries_before_success(monkeypatch):
    attempts = []
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    def respond(request, timeout):
        attempts.append(request)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(
                request.full_url, 503, "unavailable", None, None
            )
        return io.BytesIO(b'{"message": {"content": "valid reply"}}')

    monkeypatch.setattr("urllib.request.urlopen", respond)
    complete = ollama_completion("qwen2.5-coder:14b", 0.7, 1)
    assert complete("system", "user") == "valid reply"
    assert len(attempts) == 2


def test_full_collection_resumes_only_with_matching_lock(tmp_path, monkeypatch):
    for directory in EXECUTION_INPUT_DIRECTORIES:
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    source_paths = [
        "src/evaluation/example.py",
        "src/evaluation/prior_work_planner.py",
        "src/evaluation/sticks_arm_planner.py",
        "src/evaluation/proposal_view.py",
        "src/evaluation/comparison_runner.py",
        "requirements.txt",
        "requirements.lock",
        "src/evaluation/controlled_comparison.py",
        "src/concretization/verifier.py",
        "scripts/collect_controlled_comparison.py",
        "scripts/analyze_controlled_comparison.py",
        "data/concretization/action_templates.json",
        "release/plans/C0010.procedural-plan.json",
        "release/plans/C0010.concretized-plan.json",
        "release/plans/C0010.binding-catalog.json",
    ]
    for relative_path in source_paths:
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("frozen input\n")

    monkeypatch.setattr(collector, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(collector, "ollama_model_digest", lambda model: "a" * 64)
    monkeypatch.setattr(collector, "ollama_runtime_id", lambda: "ollama:test")
    monkeypatch.setattr(
        collector, "ensure_thinking_mode_supported", lambda model, mode: None
    )
    monkeypatch.setattr(
        collector,
        "load_campaign_fixture",
        lambda campaign: SimpleNamespace(steps=[SimpleNamespace(step_id="s1")]),
    )

    def fake_completion(
        model,
        temperature,
        seed,
        expected_digest,
        thinking_mode,
        receipt_sink,
        top_p,
        expected_runtime_id,
    ):
        frozen_directory = (
            tmp_path / "release/experiments/controlled_comparison/prospective-run"
        )
        assert (frozen_directory / "comparison-manifest.json").is_file()
        assert (frozen_directory / "comparison-ledger.json").is_file()
        assert top_p == 1.0
        assert expected_runtime_id == "ollama:test"

        def complete(system_prompt, user_prompt):
            raw_output = '{"template_id":"template.valid"}'
            receipt_sink(
                GenerationReceipt(
                    request_body=json.dumps({"messages": [system_prompt, user_prompt]}),
                    response_body=json.dumps({"message": {"content": raw_output}}),
                    raw_output_sha256=hashlib.sha256(raw_output.encode()).hexdigest(),
                    recorded_at="2026-10-19T00:00:00+00:00",
                    elapsed_seconds=0.1,
                    attempt_count=1,
                )
            )
            return raw_output

        return complete

    monkeypatch.setattr(collector, "ollama_completion", fake_completion)
    observed_cells = []

    def observe(arm_id, step, fixture, seed, **kwargs):
        assert kwargs["budget_sha"] != "0" * 64
        assert kwargs["oracle_revision"] != "0" * 64
        kwargs["complete"]("system", "user")
        observed_cells.append((arm_id, seed))
        proposal = NeutralProposalRecord(
            proposal_id=f"{arm_id.value}-{seed}-{step.step_id}",
            experiment_id="prospective-run",
            campaign_id="C0010",
            step_id=step.step_id,
            arm_id=arm_id,
            seed=seed,
            technique_id="T0001",
            execution_domain="linux",
            template_id="template.valid",
            proposal_budget_sha256=kwargs["budget_sha"],
            raw_output_sha256=hashlib.sha256(
                b'{"template_id":"template.valid"}'
            ).hexdigest(),
        )
        proposal.finalize_hash()
        return StepObservation(
            campaign_id="C0010",
            arm_id=arm_id,
            seed=seed,
            step_id=step.step_id,
            emitted=True,
            abstained=False,
            oracle_admitted=True,
            template_id="template.valid",
            proposal_sha256=proposal.content_sha256,
            proposal_record=proposal,
        )

    monkeypatch.setattr(collector, "observe_step", observe)
    arguments = Namespace(
        campaigns="C0010",
        seeds=5,
        experiment_id="prospective-run",
        model="qwen2.5-coder:14b",
        temperature=0.7,
        thinking="off",
        top_p=1.0,
        shuffle_seed=20261019,
    )
    assert collector.run_full(arguments) == 0
    assert len(observed_cells) == 15
    manifest_path = (
        tmp_path
        / "release/experiments/controlled_comparison/prospective-run/manifest.json"
    )
    manifest = json.loads(manifest_path.read_text())
    assert manifest["study_scope"] == "proposal_only"
    formal_ledger = json.loads(
        (manifest_path.parent / "comparison-ledger.json").read_text()
    )
    assert len(formal_ledger["records"]) == 20
    assert all(record["status"] == "planned" for record in formal_ledger["records"])
    assert manifest["arm_ids"] == [arm_id.value for arm_id in collector.COMPARABLE_ARMS]
    cache_directory = (
        tmp_path / "release/experiments/controlled_comparison/prospective-run/cache"
    )
    cached_cell = next(cache_directory.glob("*.json"))
    assert (
        StepObservation.model_validate_json(cached_cell.read_text()).generation
        is not None
    )
    assert collector.run_full(arguments) == 0
    assert len(observed_cells) == 15

    original_cell = cached_cell.read_text()
    missing_receipt = json.loads(original_cell)
    missing_receipt["generation"] = None
    cached_cell.write_text(json.dumps(missing_receipt))
    with pytest.raises(ValueError, match="lacks a generation receipt"):
        collector.run_full(arguments)
    cached_cell.write_text(original_cell)

    arguments.temperature = 0.2
    with pytest.raises(ValueError, match="differ from frozen lock"):
        collector.run_full(arguments)
    assert len(observed_cells) == 15

    arguments.temperature = 0.7
    source_file = tmp_path / "src/evaluation/example.py"
    source_file.write_text("changed source\n")
    with pytest.raises(ValueError, match="differ from frozen lock"):
        collector.run_full(arguments)
    source_file.write_text("frozen input\n")

    leftover = cache_directory / "interrupted.json.tmp"
    leftover.write_text("incomplete")
    with pytest.raises(ValueError, match="unexpected cached cells"):
        collector.run_full(arguments)
    leftover.unlink()

    corrupted = StepObservation.model_validate_json(cached_cell.read_text())
    corrupted.seed = 99
    corrupted.proposal_record.seed = 99
    corrupted.proposal_record.finalize_hash()
    corrupted.proposal_sha256 = corrupted.proposal_record.content_sha256
    cached_cell.write_text(corrupted.model_dump_json())
    with pytest.raises(ValueError, match="cached cell identity differs"):
        collector.run_full(arguments)
