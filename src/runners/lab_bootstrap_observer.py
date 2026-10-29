"""Observe granted laboratory shell access without claiming adversarial access."""

import json
import shlex

from pydantic import BaseModel, ConfigDict

from executors.lab_transport import (
    normalize_vm_name,
    resolve_target_vm_name,
    run_bash_on_target_vm,
)
from loaders.campaign_loader import load_sut_profile
from runners.capability_facts import FactScope, Identity
from runners.capability_observations import PredicateObservation
from runners.runtime_diagnostics import parse_guest_reply


class GuestShellIdentity(BaseModel):
    """Identity returned by the bounded guest probe."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    hostname: Identity
    principal: Identity
    boot_id: Identity
    nonce: Identity


def _check_profile_principal(profile_id: str, host_id: str, principal: str) -> None:
    selected = resolve_target_vm_name(profile_id)
    if host_id != selected:
        raise ValueError("Bootstrap host must match the selected profile target")
    profile = load_sut_profile(profile_id)
    accounts = {
        user.username
        for name, host in profile.hosts.items()
        if normalize_vm_name(name) == selected
        for user in host.users
    }
    if principal not in accounts or principal == "root":
        raise ValueError("Bootstrap requires a declared non-root target principal")


def _probe_script(nonce: str) -> str:
    code = (
        "import json,os,pathlib,pwd,socket; "
        "print(json.dumps(dict(hostname=socket.gethostname(), "
        "principal=pwd.getpwuid(os.geteuid()).pw_name, "
        "boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(), "
        f"nonce={nonce!r})))"
    )
    return f"python3 -c {shlex.quote(code)}"


def observe_lab_shell(
    *,
    sut_profile_id: str,
    expected_host_id: str,
    principal: str,
    run_id: str,
    environment_id: str,
    epoch: str,
    nonce: str,
) -> PredicateObservation:
    """Verify guest identity, execution account, boot identity and fresh nonce.

    The epoch is the expected Linux guest boot ID obtained by the trusted lab
    lifecycle. Success establishes granted shell access, never password theft.
    """
    scope = FactScope(
        run_id=run_id,
        environment_id=environment_id,
        epoch=epoch,
        locus="target",
        host_id=expected_host_id,
        principal=principal,
    )
    expected = GuestShellIdentity(
        hostname=expected_host_id,
        principal=principal,
        boot_id=epoch,
        nonce=nonce,
    )
    _check_profile_principal(sut_profile_id, expected_host_id, principal)
    result = run_bash_on_target_vm(
        sut_profile_id,
        _probe_script(nonce),
        execution_user=principal,
        timeout=15,
    )
    details = {"returncode": result.returncode, "stderr": result.stderr}
    if result.returncode != 0:
        return PredicateObservation(
            scope=scope,
            predicate_id="shell-nonce",
            passed=False,
            established_facts=(),
            details=details,
        )
    acquired = parse_guest_reply(
        result, lambda content: GuestShellIdentity.model_validate(json.loads(content))
    )
    matched = acquired == expected
    return PredicateObservation(
        scope=scope,
        predicate_id="shell-nonce",
        passed=matched,
        established_facts=("lab:shell",) if matched else (),
        details=details | {"identity_matched": matched},
    )
