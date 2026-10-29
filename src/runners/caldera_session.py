"""Bind one campaign to an explicitly prepared isolated CALDERA session."""

import os
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

from adapters.caldera_dispatch import CalderaDispatchIntent
from adapters.caldera_operations import CalderaOperations, http_transport
from executors.lab_transport import target_command_transport, probe_vm_identity
from runners.caldera_target_transport import CalderaTargetTransport
from runners.caldera_lab_bootstrap import laboratory_transport


class CalderaSession(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    origin: str | None = None
    lab_root: Path | None = None
    binding: CalderaDispatchIntent
    target_boot_id: UUID

    @model_validator(mode="after")
    def require_one_api_transport(self):
        if (self.origin is None) == (self.lab_root is None):
            raise ValueError("Declare exactly one CALDERA API transport")
        return self


def require_session_boot(session: CalderaSession) -> None:
    nonce = uuid4().hex
    reply = probe_vm_identity(session.binding.host, nonce)
    reply.check_returncode()
    fields = reply.stdout.strip().split("\t")
    if fields != [nonce, session.binding.host, str(session.target_boot_id)]:
        raise ValueError("CALDERA session differs from the current target boot")


@contextmanager
def campaign_caldera_session(session_path: Path, record_root: Path) -> Iterator[None]:
    session = CalderaSession.model_validate_json(session_path.read_bytes())
    if session.lab_root is not None:
        api_transport = laboratory_transport(session.lab_root)
    else:
        api_key = os.environ.get("STICKS_CALDERA_API_KEY")
        if not api_key:
            raise ValueError("STICKS_CALDERA_API_KEY is required for CALDERA dispatch")
        api_transport = http_transport(session.origin, SecretStr(api_key))
    require_session_boot(session)
    client = CalderaOperations(api_transport)
    transport = CalderaTargetTransport(
        client, session.binding, record_root,
        before_dispatch=lambda: require_session_boot(session),
    )
    with target_command_transport(transport):
        yield
