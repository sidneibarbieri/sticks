"""Scoped authority contracts for runtime capability matching."""

import pytest
from pydantic import ValidationError

from runners.capability_facts import (
    CapabilityFact,
    CapabilityRequirement,
    FactScope,
    ObservationReference,
    match_requirement,
)


def scope(**changes):
    fields = dict(
        run_id="run-a",
        environment_id="lab-a",
        epoch="boot-a",
        locus="target",
        host_id="target-a",
        principal="ubuntu",
    )
    return FactScope(**(fields | changes))


def reference(**changes):
    fields = dict(
        authority_id="lab-shell",
        predicate_id="shell-nonce",
        record_path="observations/shell.json",
        record_sha256="a" * 64,
    )
    return ObservationReference(**(fields | changes))


def fact(origin="observed", **scope_changes):
    return CapabilityFact(
        name="lab:shell",
        origin=origin,
        scope=scope(**scope_changes),
        producer_occurrence=None,
        observation=reference() if origin == "observed" else None,
    )


def requirement(**scope_changes):
    return CapabilityRequirement(
        name="lab:shell",
        scope=scope(**scope_changes),
        accepted_origins=frozenset({"observed"}),
    )


@pytest.mark.parametrize(
    "origin,accepted",
    [
        ("observed", True),
        ("simulation", False),
        ("profile_declaration", False),
    ],
)
def test_controlled_requirement_accepts_only_observed_origin(origin, accepted):
    candidate = fact(origin)
    matched = match_requirement(requirement(), (candidate,))
    assert (matched is candidate) is accepted


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "run-b"),
        ("environment_id", "lab-b"),
        ("epoch", "boot-b"),
        ("host_id", "target-b"),
        ("principal", "reconuser"),
        ("principal", None),
        ("locus", "controller"),
    ],
)
def test_scope_mismatch_cannot_authorize_requirement(field, value):
    assert match_requirement(requirement(), (fact(**{field: value}),)) is None


def test_missing_principal_is_not_a_wildcard():
    assert match_requirement(requirement(principal=None), (fact(),)) is None
    independent = fact(principal=None)
    assert match_requirement(requirement(principal=None), (independent,)) is independent


def test_matching_fact_is_found_without_discarding_other_sources():
    observed = fact()
    candidates = (fact("simulation"), fact(epoch="old"), observed)
    assert match_requirement(requirement(), candidates) is observed
    assert len(candidates) == 3


def test_empty_population_does_not_satisfy_requirement():
    assert match_requirement(requirement(), ()) is None


def test_simulation_contract_explicitly_accepts_simulated_state():
    simulated = fact("simulation")
    allowed = CapabilityRequirement(
        name="lab:shell", scope=scope(), accepted_origins=frozenset({"simulation"})
    )
    assert match_requirement(allowed, (simulated,)) is simulated


def test_similarly_named_capability_does_not_match():
    candidate = CapabilityFact(
        name="lab:shell:asserted",
        origin="observed",
        scope=scope(),
        producer_occurrence=1,
        observation=reference(),
    )
    assert match_requirement(requirement(), (candidate,)) is None


@pytest.mark.parametrize("field", ["run_id", "environment_id", "epoch", "host_id"])
@pytest.mark.parametrize("value", ["", "   "])
def test_scope_rejects_empty_identity(field, value):
    with pytest.raises(ValidationError):
        scope(**{field: value})


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/a.json",
        "../a.json",
        "a/../b.json",
        "a\\b.json",
        "",
        "./a.json",
        "a//b.json",
    ],
)
def test_reference_rejects_noncanonical_relative_path(path):
    with pytest.raises(ValidationError):
        reference(record_path=path)


@pytest.mark.parametrize("digest", ["", "a" * 63, "A" * 64, "z" * 64])
def test_reference_rejects_invalid_digest(digest):
    with pytest.raises(ValidationError):
        reference(record_sha256=digest)


def test_observed_fact_requires_observation_reference():
    with pytest.raises(ValidationError):
        CapabilityFact(
            name="lab:shell",
            origin="observed",
            scope=scope(),
            producer_occurrence=None,
            observation=None,
        )


@pytest.mark.parametrize("origin", ["simulation", "profile_declaration"])
def test_nonobserved_fact_cannot_carry_observation_authority(origin):
    with pytest.raises(ValidationError):
        CapabilityFact(
            name="lab:shell",
            origin=origin,
            scope=scope(),
            producer_occurrence=None,
            observation=reference(),
        )


@pytest.mark.parametrize("origins", [frozenset(), frozenset({"trusted"})])
def test_requirement_rejects_undefined_assurance_policy(origins):
    with pytest.raises(ValidationError):
        CapabilityRequirement(name="lab:shell", scope=scope(), accepted_origins=origins)


def test_fact_rejects_unknown_origin():
    with pytest.raises(ValidationError):
        fact("trusted")


@pytest.mark.parametrize("occurrence", [0, -1, True])
def test_fact_rejects_invalid_producer_occurrence(occurrence):
    with pytest.raises(ValidationError):
        CapabilityFact(
            name="lab:shell",
            origin="observed",
            scope=scope(),
            producer_occurrence=occurrence,
            observation=reference(),
        )


def test_scope_rejects_extra_authority_field():
    with pytest.raises(ValidationError):
        scope(trusted=True)


def test_fact_identity_cannot_be_mutated_after_validation():
    candidate = fact()
    with pytest.raises(ValidationError):
        candidate.origin = "simulation"


@pytest.mark.parametrize(
    "path", ["observations/line\n.json", "observations/tab\t.json"]
)
def test_reference_rejects_control_characters_in_path(path):
    with pytest.raises(ValidationError):
        reference(record_path=path)
