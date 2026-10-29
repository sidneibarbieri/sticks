"""Bind native CALDERA completion to declared command and agent identities."""

import hashlib
from collections.abc import Callable
from typing import Annotated, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

Identity = Annotated[StrictStr, Field(min_length=1)]
Digest = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
DEFAULT_COMMAND_TIMEOUT_SECONDS = 30


class NativeRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)


class CalderaDispatchIntent(NativeRecord):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    operation_id: Identity
    group: Identity
    agent_id: Identity
    host: Identity
    principal: Identity
    platform: Identity
    executor: Identity
    command_sha256: Digest
    timeout_seconds: Annotated[StrictInt, Field(gt=0, le=300)] = DEFAULT_COMMAND_TIMEOUT_SECONDS

    def bind_link(self, link_id: str) -> "CalderaDispatchExpectation":
        return CalderaDispatchExpectation(**self.model_dump(), link_id=link_id)


class CalderaDispatchExpectation(CalderaDispatchIntent):
    link_id: Identity


class NativeExecutor(NativeRecord):
    name: Identity
    platform: Identity
    timeout: Annotated[StrictInt, Field(gt=0)]


class NativeLink(NativeRecord):
    id: Identity
    paw: Identity
    host: Identity
    command: Identity
    plaintext_command: Identity
    executor: NativeExecutor
    status: StrictInt
    finish: StrictStr | None


class NativeAgent(NativeRecord):
    paw: Identity
    group: Identity
    host: Identity
    username: Identity
    platform: Identity
    trusted: StrictBool
    executors: tuple[Identity, ...]


class NativeOperation(NativeRecord):
    id: Identity
    group: Identity
    state: Identity
    obfuscator: Identity
    chain: tuple[NativeLink, ...]
    host_group: tuple[NativeAgent, ...]


class CalderaDispatchReceipt(CalderaDispatchExpectation):
    schema_version: Literal["caldera-dispatch-receipt/v1"] = "caldera-dispatch-receipt/v1"
    assurance: Literal["native_command_completed"] = "native_command_completed"
    finished_at: Identity


def command_digest(command: str) -> str:
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


Record = TypeVar("Record", bound=NativeRecord)


def _select_identity(
    items: tuple[Record, ...], identity: str, key: Callable[[Record], str], condition: str
) -> Record:
    selected = [item for item in items if key(item) == identity]
    if len(selected) != 1:
        raise ValueError(f"CALDERA dispatch condition failed: {condition}")
    return selected[0]


def verify_completed_dispatch(
    expected: CalderaDispatchExpectation, payload: object
) -> CalderaDispatchReceipt:
    """Check the native ledger; this does not assert an independently observed effect."""
    operation = NativeOperation.model_validate(payload)
    link = _select_identity(operation.chain, expected.link_id, lambda item: item.id, "unique_link")
    agent = _select_identity(operation.host_group, expected.agent_id, lambda item: item.paw, "unique_agent")
    conditions = (
        ("operation_identity", operation.id == expected.operation_id),
        ("operation_group", operation.group == expected.group),
        ("operation_state", operation.state in {"running", "finished"}),
        ("plain_command_policy", operation.obfuscator == "plain-text"),
        ("agent_identity", link.paw == expected.agent_id),
        ("agent_group", agent.group == expected.group),
        ("agent_trusted", agent.trusted),
        ("target_identity", link.host == agent.host == expected.host),
        ("principal", agent.username == expected.principal),
        ("platform", agent.platform == link.executor.platform == expected.platform),
        ("executor", link.executor.name == expected.executor and expected.executor in agent.executors),
        ("executor_timeout", link.executor.timeout == expected.timeout_seconds),
        ("command_digest", command_digest(link.command) == expected.command_sha256),
        ("plaintext_digest", command_digest(link.plaintext_command) == expected.command_sha256),
        ("completion_status", link.status == 0),
        ("finish_timestamp", link.finish is not None and bool(link.finish.strip())),
    )
    failed = tuple(name for name, passed in conditions if not passed)
    if failed:
        raise ValueError("CALDERA dispatch conditions failed: " + ", ".join(failed))
    return CalderaDispatchReceipt(**expected.model_dump(), finished_at=link.finish)
