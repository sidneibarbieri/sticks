"""Typed STIX custom properties for auditable procedural semantics."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


PROCEDURE_PROPERTY = "x_sticks_procedure"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueOrigin(str, Enum):
    stix = "stix"
    deterministic_compiler = "deterministic_compiler"
    finite_domain_solver = "finite_domain_solver"
    verified_llm_proposal = "verified_llm_proposal"
    analyst_reference = "analyst_reference"


class FieldProvenance(StrictModel):
    origin: ValueOrigin
    source_ids: list[str] = Field(min_length=1)
    source_sha256: str
    method: str


class ProcedureSemantics(StrictModel):
    schema_version: str = "1"
    sequence: int = Field(ge=1)
    technique_id: str
    action_template_id: str
    parameter_kinds: dict[str, str]
    requires: list[str]
    produces: list[str] = Field(min_length=1)
    evidence_predicates: list[str] = Field(min_length=1)
    fidelity_ceiling: str
    proposal_source: str
    provenance: FieldProvenance
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.content_sha256 = hashlib.sha256(encoded).hexdigest()

    def validate_hash(self) -> bool:
        expected = self.content_sha256
        self.finalize_hash()
        return self.content_sha256 == expected

    @model_validator(mode="after")
    def validate_parameter_names(self) -> "ProcedureSemantics":
        if any(not name.strip() for name in self.parameter_kinds):
            raise ValueError("parameter names must be non-empty")
        return self


def parse_procedure_property(relationship: dict[str, Any]) -> ProcedureSemantics | None:
    payload = relationship.get(PROCEDURE_PROPERTY)
    if payload is None:
        return None
    extension = ProcedureSemantics.model_validate(payload)
    if not extension.validate_hash():
        raise ValueError(
            f"procedure extension hash mismatch: {relationship.get('id', '<unknown>')}"
        )
    return extension

