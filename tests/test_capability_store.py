"""Store preserves provenance and accepts only registered observation evidence."""

import json
import subprocess
from datetime import datetime

import pytest
from pydantic import ValidationError

from executors.models import CampaignEvidence, RuntimeCampaignEvidence
from runners.capability_authority import LabShellRequest, acquire_registered_observation
from runners.capability_facts import CapabilityFact, CapabilityRequirement, FactScope
from runners.capability_observations import PredicateObservation, retain_observation
from runners.capability_store import CapabilityStore


def scope(**changes):
    return FactScope(
        **(
            dict(
                run_id="run-a",
                environment_id="lab-a",
                epoch="boot-a",
                locus="target",
                host_id="target-linux-1",
                principal="ubuntu",
            )
            | changes
        )
    )


def fact(origin, **changes):
    return CapabilityFact(
        name="lab:shell",
        origin=origin,
        scope=scope(**changes),
        producer_occurrence=None,
        observation=None,
    )


def acquisition(monkeypatch, tmp_path, passed=True):
    def probe(*args, **kwargs):
        reply = json.dumps(
            dict(
                hostname="target-linux-1",
                principal="ubuntu",
                boot_id="boot-a",
                nonce="nonce-a",
            )
        )
        return subprocess.CompletedProcess(["probe"], 0 if passed else 17, reply, "")

    monkeypatch.setattr("runners.lab_bootstrap_observer.run_bash_on_target_vm", probe)
    request = LabShellRequest(sut_profile_id="0.c0026", scope=scope(), nonce="nonce-a")
    return acquire_registered_observation("lab-shell", request, run_root=tmp_path)


def ingest(store, reference, tmp_path):
    return store.add_observed(
        reference,
        run_root=tmp_path,
        expected_scope=scope(),
        expected_predicate="shell-nonce",
    )


def test_store_retains_same_name_from_distinct_origins(monkeypatch, tmp_path):
    store = CapabilityStore()
    store.add_declaration(fact("profile_declaration"))
    store.add_simulation(fact("simulation"))
    acquired = ingest(store, acquisition(monkeypatch, tmp_path), tmp_path)
    assert [item.origin for item in store.snapshot()] == [
        "profile_declaration",
        "simulation",
        "observed",
    ]
    required = CapabilityRequirement(
        name="lab:shell", scope=scope(), accepted_origins={"observed"}
    )
    assert store.match(required) == acquired[0]


def test_unregistered_stored_claim_cannot_be_ingested(tmp_path):
    claimed = PredicateObservation(
        scope=scope(),
        predicate_id="shell-nonce",
        passed=True,
        established_facts=("lab:shell",),
        details={},
    )
    reference = retain_observation(claimed, authority_id="lab-shell", run_root=tmp_path)
    store = CapabilityStore()
    with pytest.raises((ValueError, FileNotFoundError)):
        ingest(store, reference, tmp_path)
    assert store.snapshot() == ()


def test_failed_registered_acquisition_creates_no_facts(monkeypatch, tmp_path):
    store = CapabilityStore()
    assert (
        ingest(store, acquisition(monkeypatch, tmp_path, passed=False), tmp_path) == ()
    )
    assert store.snapshot() == ()


def test_invalidation_preserves_unrelated_controller_scope(monkeypatch, tmp_path):
    store = CapabilityStore()
    controller = fact(
        "profile_declaration", locus="controller", host_id="control-a", principal=None
    )
    store.add_declaration(controller)
    ingest(store, acquisition(monkeypatch, tmp_path), tmp_path)
    store.invalidate(scope())
    assert store.snapshot() == (controller,)


def test_declaration_api_refuses_observed_fact(monkeypatch, tmp_path):
    store = CapabilityStore()
    observed = ingest(store, acquisition(monkeypatch, tmp_path), tmp_path)[0]
    with pytest.raises(ValueError):
        store.add_declaration(observed)
    with pytest.raises(ValueError):
        store.add_simulation(observed)


def test_repeated_ingestion_does_not_duplicate_same_acquisition(monkeypatch, tmp_path):
    store = CapabilityStore()
    reference = acquisition(monkeypatch, tmp_path)
    ingest(store, reference, tmp_path)
    ingest(store, reference, tmp_path)
    assert len(store.snapshot()) == 1


def test_legacy_evidence_cannot_be_promoted_by_missing_version():
    legacy = dict(
        campaign_id="0.c0026",
        sut_profile_id="0.c0026",
        start_time=datetime(2026, 1, 1),
        successful=6,
        accumulated_capabilities=["access:initial", "code_execution"],
    )
    restored = CampaignEvidence.model_validate(legacy)
    assert restored.successful == 6
    assert restored.accumulated_capabilities == ["access:initial", "code_execution"]
    with pytest.raises(ValidationError):
        RuntimeCampaignEvidence.model_validate(legacy)
    assert CapabilityStore().snapshot() == ()


def test_explicit_runtime_evidence_round_trips_without_origin_upgrade():
    record = RuntimeCampaignEvidence(
        schema_version="runtime-facts/v2",
        campaign_id="0.c0026",
        sut_profile_id="0.c0026",
        start_time=datetime(2026, 1, 1),
        runtime_facts=(fact("simulation"),),
    )
    restored = RuntimeCampaignEvidence.model_validate_json(record.model_dump_json())
    assert restored.runtime_facts[0].origin == "simulation"
    assert restored.schema_version == "runtime-facts/v2"


def test_altered_acquisition_cannot_partially_update_store(monkeypatch, tmp_path):
    store = CapabilityStore()
    declared = fact("profile_declaration")
    store.add_declaration(declared)
    reference = acquisition(monkeypatch, tmp_path)
    (tmp_path / reference.record_path).write_bytes(b"{}")
    with pytest.raises(ValueError):
        ingest(store, reference, tmp_path)
    assert store.snapshot() == (declared,)


def test_previous_boot_acquisition_cannot_update_current_scope(monkeypatch, tmp_path):
    store = CapabilityStore()
    reference = acquisition(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        store.add_observed(
            reference,
            run_root=tmp_path,
            expected_scope=scope(epoch="boot-b"),
            expected_predicate="shell-nonce",
        )
    assert store.snapshot() == ()
