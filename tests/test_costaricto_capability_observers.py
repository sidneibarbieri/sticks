"""CostaRicto facts require a registered, boot-bound guest acquisition."""

import hashlib
import json
import subprocess

import pytest
from pydantic import ValidationError

from runners.capability_authority import (
    acquire_registered_observation,
    verify_registered_observation,
)
from runners.capability_facts import FactScope
from runners.costaricto_capability_observers import (
    CostaRictoEffectRequest,
    observe_costaricto_effect,
)


def request(predicate_id: str = "benign-transfer") -> CostaRictoEffectRequest:
    occurrence = {
        "local-service-listing": 1,
        "benign-transfer": 2,
        "local-collection": 9,
    }[predicate_id]
    return CostaRictoEffectRequest(
        sut_profile_id="0.costaricto",
        scope=FactScope(
            run_id="run-a",
            environment_id="lab-a",
            epoch="boot-a",
            locus="target",
            host_id="target-linux-1",
            principal="reconuser",
        ),
        nonce="nonce-a",
        predicate_id=predicate_id,
        producer_occurrence=occurrence,
    )


def install_reply(monkeypatch, predicate_id: str, **changes) -> None:
    digest = hashlib.sha256(b"declared fixture").hexdigest()

    def probe(profile_id, script, **kwargs):
        assert profile_id == "0.costaricto"
        assert kwargs["execution_user"] == "reconuser"
        assert "costaricto_predicates" in script
        reply = {
            "hostname": "target-linux-1",
            "principal": "reconuser",
            "boot_id": "boot-a",
            "nonce": "nonce-a",
            "predicate_id": predicate_id,
            "passed": True,
            "measurements": {
                "passed": True,
                "content_sha256": digest,
                "input_sha256": digest,
            },
        }
        return subprocess.CompletedProcess([], 0, json.dumps(reply | changes), "")

    monkeypatch.setattr(
        "runners.costaricto_capability_observers.run_bash_on_target_vm", probe
    )


@pytest.mark.parametrize(
    "predicate_id,authority,product",
    [
        (
            "local-service-listing",
            "costaricto-discovery",
            "discovery:declared_guest_listeners_recorded",
        ),
        ("benign-transfer", "costaricto-transfer", "transfer:guest_loopback_verified"),
        (
            "local-collection",
            "costaricto-collection",
            "collection:fixture_copy_verified",
        ),
    ],
)
def test_registered_observation_retains_only_its_bound_product(
    monkeypatch, tmp_path, predicate_id, authority, product
):
    selected = request(predicate_id)
    install_reply(monkeypatch, predicate_id)
    reference = acquire_registered_observation(authority, selected, run_root=tmp_path)
    observed = verify_registered_observation(
        reference,
        run_root=tmp_path,
        expected_scope=selected.scope,
        expected_predicate=predicate_id,
    )
    assert observed.passed
    assert observed.producer_occurrence == selected.producer_occurrence
    assert observed.established_facts == (product,)


@pytest.mark.parametrize("change", [{"boot_id": "old-boot"}, {"nonce": "old"}])
def test_wrong_guest_identity_grants_nothing(monkeypatch, change):
    selected = request()
    install_reply(monkeypatch, selected.predicate_id, **change)
    observed = observe_costaricto_effect(selected)
    assert not observed.passed
    assert observed.established_facts == ()


def test_wrong_producer_occurrence_is_rejected():
    with pytest.raises(ValidationError):
        CostaRictoEffectRequest.model_validate(
            request().model_dump() | {"producer_occurrence": 9}
        )


def test_measurement_rejection_grants_nothing(monkeypatch):
    selected = request()
    install_reply(
        monkeypatch,
        selected.predicate_id,
        measurements={
            "passed": False,
            "content_sha256": "0" * 64,
            "input_sha256": "0" * 64,
        },
    )
    observed = observe_costaricto_effect(selected)
    assert not observed.passed
    assert observed.established_facts == ()
