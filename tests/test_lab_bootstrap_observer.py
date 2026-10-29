"""Bootstrap checks at the guest transport boundary."""

import json
import subprocess

import pytest

from runners.lab_bootstrap_observer import observe_lab_shell


def observe():
    return observe_lab_shell(
        sut_profile_id="0.c0026",
        expected_host_id="target-linux-1",
        principal="ubuntu",
        run_id="run-a",
        environment_id="lab-a",
        epoch="boot-a",
        nonce="nonce-a",
    )


def guest_reply(**changes):
    fields = dict(
        hostname="target-linux-1", principal="ubuntu", boot_id="boot-a", nonce="nonce-a"
    )
    return json.dumps(fields | changes)


def transport(monkeypatch, reply, returncode=0):
    def run(
        sut_profile_id, bash_script, timeout=45, provider=None, execution_user=None
    ):
        assert sut_profile_id == "0.c0026"
        assert execution_user == "ubuntu"
        assert "nonce-a" in bash_script
        return subprocess.CompletedProcess(
            ["guest-probe"], returncode, reply, "probe-stderr"
        )

    monkeypatch.setattr("runners.lab_bootstrap_observer.run_bash_on_target_vm", run)


def test_matching_guest_principal_boot_and_nonce_establish_granted_shell(monkeypatch):
    transport(monkeypatch, guest_reply())
    acquired = observe()
    assert acquired.passed is True
    assert acquired.established_facts == ("lab:shell",)
    assert acquired.scope.principal == "ubuntu"
    assert acquired.scope.epoch == "boot-a"


@pytest.mark.parametrize(
    "changes",
    [
        {"hostname": "other-guest"},
        {"principal": "vagrant"},
        {"boot_id": "old-boot"},
        {"nonce": "old-nonce"},
    ],
)
def test_mismatched_guest_identity_cannot_authorize_shell(monkeypatch, changes):
    transport(monkeypatch, guest_reply(**changes))
    acquired = observe()
    assert acquired.passed is False
    assert acquired.established_facts == ()


def test_nonzero_probe_preserves_failure_without_shell_fact(monkeypatch):
    transport(monkeypatch, guest_reply(), returncode=17)
    acquired = observe()
    assert acquired.passed is False
    assert acquired.established_facts == ()
    assert acquired.details["returncode"] == 17
    assert acquired.details["stderr"] == "probe-stderr"


def test_transport_exception_is_not_converted_to_success(monkeypatch):
    failure = TimeoutError("guest probe timeout")

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr("runners.lab_bootstrap_observer.run_bash_on_target_vm", fail)
    with pytest.raises(TimeoutError) as caught:
        observe()
    assert caught.value is failure


def test_unknown_principal_is_rejected_before_transport():
    with pytest.raises(ValueError):
        observe_lab_shell(
            sut_profile_id="0.c0026",
            expected_host_id="target-linux-1",
            principal="unknown-user",
            run_id="run-a",
            environment_id="lab-a",
            epoch="boot-a",
            nonce="nonce-a",
        )


def test_wrong_profile_target_is_rejected_before_transport():
    with pytest.raises(ValueError):
        observe_lab_shell(
            sut_profile_id="0.c0026",
            expected_host_id="other-host",
            principal="ubuntu",
            run_id="run-a",
            environment_id="lab-a",
            epoch="boot-a",
            nonce="nonce-a",
        )


def test_malformed_reply_preserves_parse_failure(monkeypatch):
    transport(monkeypatch, "not-json")
    with pytest.raises(ValueError):
        observe()
