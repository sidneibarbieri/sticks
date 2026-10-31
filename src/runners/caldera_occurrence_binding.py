"""Retain a command's declared occurrence separately from native completion."""

from typing import Literal

from pydantic import Field

from runners.capability_facts import Digest, ImmutableRecord
from runners.runtime_step_contracts import RuntimeStepContract


class CalderaOccurrenceBinding(ImmutableRecord):
    schema_version: Literal["caldera-occurrence-binding/v1"] = Field(
        default="caldera-occurrence-binding/v1", alias="schema"
    )
    contract: RuntimeStepContract
    command_sha256: Digest
