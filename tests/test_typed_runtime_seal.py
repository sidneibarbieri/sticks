"""Typed completion sealing rejects unbound or merely asserted successes."""

import hashlib
import json
import shutil
from types import SimpleNamespace
from pathlib import Path

import pytest

from tests.test_c0026_public_runtime import guest_fixture
from runners.campaign_runner import UnifiedCampaignRunner
from scripts.typed_runtime_seal import (
    _C0045_EVIDENCE_SOURCE_PATHS,
    _bound_c0045_population,
    validate_typed_completion,
)
from runners.runtime_journal import RuntimeJournalRecord, retain_runtime_record
from runners import campaign_runner


def prepared(tmp_path, monkeypatch):
    guest_fixture(monkeypatch, tmp_path)
    runner = UnifiedCampaignRunner("0.c0026", tmp_path / "evidence", require_lab=True)
    runner.run()
    source_root = Path(__file__).resolve().parent.parent
    workspace = tmp_path / "workspace"
    entries = []
    for name in (
        "data/runtime_contracts/c0026.json",
        "src/executors/executor_registry.py",
        "src/executors/legacy_parity_expansion_executors.py",
    ):
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / name, target)
        entries.append(
            {"path": name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        )
    payload = json.loads((runner.evidence_dir / "summary.json").read_text())
    return payload, runner.evidence_dir, workspace, {"files": entries}


def test_typed_completion_requires_bound_acquisitions(monkeypatch, tmp_path):
    payload, evidence, workspace, manifest = prepared(tmp_path, monkeypatch)
    result = validate_typed_completion(payload, evidence, workspace, manifest)
    assert result.effects_observed == 5
    assert result.simulated == 1


def test_forged_aggregate_counter_is_refused(monkeypatch, tmp_path):
    payload, evidence, workspace, manifest = prepared(tmp_path, monkeypatch)
    payload["effects_observed"] = 6
    with pytest.raises(ValueError):
        validate_typed_completion(payload, evidence, workspace, manifest)


def test_missing_registered_observation_is_refused(monkeypatch, tmp_path):
    payload, evidence, workspace, manifest = prepared(tmp_path, monkeypatch)
    reference = payload["steps"][3]["outcome"]["observation_references"][0]
    (evidence / reference["record_path"]).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        validate_typed_completion(payload, evidence, workspace, manifest)


def test_one_occurrence_cannot_be_omitted_from_seal(monkeypatch, tmp_path):
    payload, evidence, workspace, manifest = prepared(tmp_path, monkeypatch)
    payload["steps"].pop()
    payload["total_techniques"] = 5
    payload["effects_observed"] = 4
    with pytest.raises(ValueError):
        validate_typed_completion(payload, evidence, workspace, manifest)


@pytest.mark.parametrize(
    "alteration",
    [
        "producer",
        "consumed_input",
        "freshness",
        "product_digest",
        "terminal_checkpoint",
        "technique",
        "guest_epoch",
    ],
)
def test_inconsistent_provenance_is_refused(monkeypatch, tmp_path, alteration):
    payload, evidence, workspace, manifest = prepared(tmp_path, monkeypatch)
    if alteration == "producer":
        payload["steps"][3]["outcome"]["observations"][0]["producer_occurrence"] = 2
    elif alteration == "consumed_input":
        payload["steps"][4]["outcome"]["consumed_references"].pop()
    elif alteration == "freshness":
        payload["steps"][4]["revalidation_references"] = []
    elif alteration == "product_digest":
        payload["steps"][3]["outcome"]["authorizing_facts"][0]["content_sha256"] = (
            "f" * 64
        )
    elif alteration == "terminal_checkpoint":
        payload["journal_references"].pop()
    elif alteration == "technique":
        payload["steps"][3]["contract"]["technique_id"] = "T1059"
    else:
        payload["steps"][3]["contract"]["scope"]["epoch"] = "another-boot"
    with pytest.raises(ValueError):
        validate_typed_completion(payload, evidence, workspace, manifest)


def test_sealed_executor_bytes_cannot_be_replaced(monkeypatch, tmp_path):
    payload, evidence, workspace, manifest = prepared(tmp_path, monkeypatch)
    (workspace / "src/executors/executor_registry.py").write_text("replaced source")
    with pytest.raises(ValueError):
        validate_typed_completion(payload, evidence, workspace, manifest)


@pytest.mark.parametrize(
    "alteration", ["replayed_revalidation", "failed_return", "unlisted_error"]
)
def test_reviewed_journal_inconsistencies_are_refused(
    monkeypatch, tmp_path, alteration
):
    payload, evidence, workspace, manifest = prepared(tmp_path, monkeypatch)
    if alteration == "replayed_revalidation":
        step = payload["steps"][4]
        step["revalidation_references"] = [step["outcome"]["consumed_references"][1]]
        for reference in payload["journal_references"][:]:
            raw = json.loads((evidence / reference["record_path"]).read_text())
            if raw["contract"]["occurrence"] == 5:
                raw["revalidation_references"] = step["revalidation_references"]
                replacement = retain_runtime_record(
                    RuntimeJournalRecord.model_validate(raw), run_root=evidence
                )
                payload["journal_references"][
                    payload["journal_references"].index(reference)
                ] = replacement.model_dump(mode="json")
                (evidence / reference["record_path"]).unlink()
        with pytest.raises(ValueError, match="fresh"):
            validate_typed_completion(payload, evidence, workspace, manifest)
        return
    phase = "executor_completed" if alteration == "failed_return" else "observed"
    occurrence = 4 if alteration == "failed_return" else 6
    selected = next(
        reference
        for reference in payload["journal_references"]
        if (record := json.loads((evidence / reference["record_path"]).read_text()))[
            "phase"
        ]
        == phase
        and record["contract"]["occurrence"] == occurrence
    )
    raw = json.loads((evidence / selected["record_path"]).read_text())
    if alteration == "failed_return":
        raw["invocation"]["executor_completed"] = False
        replacement = retain_runtime_record(
            RuntimeJournalRecord.model_validate(raw), run_root=evidence
        )
        payload["journal_references"][payload["journal_references"].index(selected)] = (
            replacement.model_dump(mode="json")
        )
        (evidence / selected["record_path"]).unlink()
    else:
        raw.update(
            phase="error", error_type="OSError", error_message="later interruption"
        )
        retain_runtime_record(
            RuntimeJournalRecord.model_validate(raw), run_root=evidence
        )
    with pytest.raises(ValueError):
        validate_typed_completion(payload, evidence, workspace, manifest)


def test_revalidation_acquired_for_another_consumer_is_refused(monkeypatch, tmp_path):
    original = campaign_runner.effect_request

    def wrong_consumer(*args, **kwargs):
        if kwargs.get("consumer_occurrence") == 5:
            kwargs["consumer_occurrence"] = 6
        return original(*args, **kwargs)

    monkeypatch.setattr(campaign_runner, "effect_request", wrong_consumer)
    payload, evidence, workspace, manifest = prepared(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="dependent occurrence"):
        validate_typed_completion(payload, evidence, workspace, manifest)


def test_non_uuid_run_cannot_receive_typed_completion(monkeypatch, tmp_path):
    monkeypatch.setattr(
        campaign_runner, "uuid4", lambda: SimpleNamespace(hex="not-a-uuid")
    )
    payload, evidence, workspace, manifest = prepared(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="UUID"):
        validate_typed_completion(payload, evidence, workspace, manifest)


def _c0045_workspace(tmp_path):
    source_root = Path(__file__).resolve().parent.parent
    workspace = tmp_path / "c0045-workspace"
    entries = []
    for name in (
        "data/runtime_contracts/c0045_v2.json",
        "src/executors/shadowray_fixed_executors.py",
        "src/executors/privilege_escalation_executors.py",
        *_C0045_EVIDENCE_SOURCE_PATHS,
    ):
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / name, target)
        entries.append(
            {"path": name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        )
    return workspace, {"files": entries}


def test_c0045_population_requires_bound_full_causal_permutation(tmp_path):
    workspace, manifest = _c0045_workspace(tmp_path)
    population = _bound_c0045_population(workspace, manifest)
    assert [row.occurrence for row in population.occurrences] == list(range(1, 11))
    assert sorted(row.plan_sequence for row in population.occurrences) == list(
        range(1, 11)
    )


def test_c0045_population_rejects_a_nonpermutation_after_source_binding(tmp_path):
    workspace, manifest = _c0045_workspace(tmp_path)
    contract_path = workspace / "data/runtime_contracts/c0045_v2.json"
    document = json.loads(contract_path.read_text())
    document["occurrences"][0]["plan_sequence"] = 1
    contract_path.write_text(json.dumps(document))
    manifest["files"][0]["sha256"] = hashlib.sha256(
        contract_path.read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError, match="causal permutation"):
        _bound_c0045_population(workspace, manifest)


@pytest.mark.parametrize(
    "path",
    (
        "src/executors/c0045_trace_executor.py",
        "src/runners/c0045_trace_observer.py",
        "src/runners/capability_authority.py",
        "src/runners/campaign_runner.py",
        "src/runners/guest_execution_trace.py",
    ),
)
def test_c0045_population_rejects_observer_semantic_drift(tmp_path, path):
    workspace, manifest = _c0045_workspace(tmp_path)
    target = workspace / path
    target.write_bytes(target.read_bytes() + b"\n# altered\n")
    with pytest.raises(ValueError, match="differs from the source manifest"):
        _bound_c0045_population(workspace, manifest)
