"""Typed procedural representation compiled from an ATT&CK STIX bundle."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field


class SourceSnapshot(BaseModel):
    bundle_sha256: str
    object_count: int
    campaign_stix_id: str
    campaign_external_id: str


class ProcedureStep(BaseModel):
    technique_id: str
    technique_stix_id: str
    name: str
    execution_domain: str
    tactics: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    permissions_required: list[str] = Field(default_factory=list)
    system_requirements: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(min_length=1)
    procedure_descriptions: list[str] = Field(default_factory=list)


class ProceduralPlan(BaseModel):
    schema_version: str = "1"
    compiler_version: str = "1"
    campaign_id: str
    campaign_name: str
    source: SourceSnapshot
    ordering_policy: str = "tactic_rank_then_technique_id"
    steps: list[ProcedureStep] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
    content_sha256: str = ""

    def _computed_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def finalize_hash(self) -> None:
        self.content_sha256 = self._computed_hash()

    def validate_hash(self) -> bool:
        return bool(self.content_sha256) and self.content_sha256 == self._computed_hash()
