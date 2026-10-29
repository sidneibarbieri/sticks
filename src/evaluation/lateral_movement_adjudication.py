"""Protocol-bound human adjudication for the P16 lexical screen.

The lateral-movement grounding record is deliberately a deterministic lexical screen.  It
is useful for finding the small set of procedure descriptions that merit close reading, but
it is not evidence that the lexical labels are semantically correct.  This module keeps the
two layers separate:

* the screen remains reproducible from the pinned plans; and
* a paper-facing P16 claim becomes eligible only after independently recorded human labels
  cover the frozen, blind task packet and confirm the screen's labels.

The public records contain opaque annotator identifiers rather than names, e-mail addresses,
or free-form comments.  That protects annotator privacy, but it does not magically prove
independence; the gate reports the recorded attestations and requires distinct identifiers.
The protocol describes the remaining process requirement explicitly.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PROTOCOL_SCHEMA_VERSION = "1.0.0"
TASK_PACKET_SCHEMA_VERSION = "1.0.0"
ANNOTATION_SCHEMA_VERSION = "1.0.0"
STATUS_SCHEMA_VERSION = "1.0.0"


class StrictModel(BaseModel):
    """Reject untracked fields in evidence contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdjudicationLabel(str, Enum):
    """Human labels for the meaning of one lateral-movement description."""

    credential_reuse = "credential_reuse"
    independent_mechanism = "independent_mechanism"
    insufficient_evidence = "insufficient_evidence"


LEXICAL_TO_ADJUDICATION_LABEL = {
    "cti": AdjudicationLabel.credential_reuse,
    "independent_mechanism": AdjudicationLabel.independent_mechanism,
    "procedure_dependency": AdjudicationLabel.insufficient_evidence,
}


class RationaleCode(str, Enum):
    """Closed rationale vocabulary prevents identity-bearing free-form annotations."""

    explicit_credential_reuse = "explicit_credential_reuse"
    explicit_independent_mechanism = "explicit_independent_mechanism"
    insufficient_textual_link = "insufficient_textual_link"


class TextSpan(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def _end_follows_start(self) -> "TextSpan":
        if self.end <= self.start:
            raise ValueError("annotation span end must follow its start")
        return self


class P16AdjudicationProtocol(StrictModel):
    """Versioned decision rule for validating P16 annotations."""

    schema_version: str
    protocol_id: str
    claim_id: str
    source_record_path: str
    task_packet_path: str
    records_directory: str
    status_path: str
    minimum_annotators: int = Field(ge=2)
    minimum_pairwise_exact_agreement: float = Field(ge=0.0, le=1.0)
    require_full_coverage: bool
    require_lexical_concordance: bool
    blind_to_lexical_screen: bool
    identity_policy: str
    independence_requirement: str
    labels: dict[AdjudicationLabel, str]

    @model_validator(mode="after")
    def _validate_protocol_version(self) -> "P16AdjudicationProtocol":
        if self.schema_version != PROTOCOL_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported P16 adjudication protocol schema: {self.schema_version}"
            )
        if self.claim_id != "STICKS-P16":
            raise ValueError("the P16 protocol must bind STICKS-P16")
        if set(self.labels) != set(AdjudicationLabel):
            raise ValueError("the P16 protocol must define every adjudication label")
        return self


class TaskPacketItem(StrictModel):
    """One blinded procedure description supplied to an annotator."""

    item_id: str
    campaign_id: str
    technique_id: str
    procedure_excerpt: str = Field(min_length=1)
    procedure_excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _verify_excerpt_digest(self) -> "TaskPacketItem":
        if self.procedure_excerpt_sha256 != sha256_text(self.procedure_excerpt):
            raise ValueError("task-packet procedure excerpt digest does not match its text")
        return self


class P16TaskPacket(StrictModel):
    """A frozen, lexical-label-free annotation packet."""

    schema_version: str
    protocol_id: str
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: list[TaskPacketItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_packet(self) -> "P16TaskPacket":
        if self.schema_version != TASK_PACKET_SCHEMA_VERSION:
            raise ValueError(f"unsupported P16 task-packet schema: {self.schema_version}")
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("task packet contains duplicate item identifiers")
        return self


class AnnotationDecision(StrictModel):
    """One opaque, source-anchored annotation decision."""

    item_id: str
    label: AdjudicationLabel
    rationale_codes: list[RationaleCode] = Field(min_length=1)
    evidence_spans: list[TextSpan] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_label_rationale(self) -> "AnnotationDecision":
        required = {
            AdjudicationLabel.credential_reuse: RationaleCode.explicit_credential_reuse,
            AdjudicationLabel.independent_mechanism: RationaleCode.explicit_independent_mechanism,
            AdjudicationLabel.insufficient_evidence: RationaleCode.insufficient_textual_link,
        }[self.label]
        if set(self.rationale_codes) != {required}:
            raise ValueError("annotation rationale code does not match its label")
        if self.label is AdjudicationLabel.insufficient_evidence and self.evidence_spans:
            raise ValueError("insufficient-evidence labels must not invent an evidence span")
        if self.label is not AdjudicationLabel.insufficient_evidence and not self.evidence_spans:
            raise ValueError("affirmative labels require a source-text span")
        return self


class P16AnnotationRecord(StrictModel):
    """One identity-free annotation record submitted under the frozen protocol."""

    schema_version: str
    protocol_id: str
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotator_id: str = Field(pattern=r"^annotator-[a-f0-9]{8,64}$")
    independence_attestation: bool
    annotations: list[AnnotationDecision] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_record(self) -> "P16AnnotationRecord":
        if self.schema_version != ANNOTATION_SCHEMA_VERSION:
            raise ValueError(f"unsupported P16 annotation schema: {self.schema_version}")
        item_ids = [annotation.item_id for annotation in self.annotations]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("annotation record contains duplicate item identifiers")
        return self


class PairwiseAgreement(StrictModel):
    """Exact agreement for one pair of opaque annotator records."""

    annotator_a: str
    annotator_b: str
    exact_agreement: float = Field(ge=0.0, le=1.0)
    matching_items: int = Field(ge=0)
    total_items: int = Field(gt=0)


class P16AdjudicationStatus(StrictModel):
    """Machine-readable decision on whether the current P16 statement is paper eligible."""

    schema_version: str
    claim_id: str
    protocol_id: str
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lexical_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lexical_item_count: int = Field(ge=1)
    annotation_record_count: int = Field(ge=0)
    distinct_annotator_count: int = Field(ge=0)
    all_records_attest_independence: bool
    pairwise_agreement: list[PairwiseAgreement]
    lexical_concordance: float | None = Field(default=None, ge=0.0, le=1.0)
    status: str
    paper_eligible: bool
    reasons: list[str]

    @model_validator(mode="after")
    def _validate_status(self) -> "P16AdjudicationStatus":
        if self.schema_version != STATUS_SCHEMA_VERSION:
            raise ValueError(f"unsupported P16 status schema: {self.schema_version}")
        expected = self.status == "qualified"
        if self.paper_eligible != expected:
            raise ValueError("paper eligibility must be true exactly for qualified status")
        return self


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical_json_sha256(value: Any) -> str:
    """Hash JSON content independent of whitespace and object insertion order."""

    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_text(rendered)


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _item_id(step: dict[str, Any], occurrence: int) -> str:
    return f"{step['campaign_id']}:{step['technique_id']}:{occurrence:02d}"


def build_task_packet(
    lexical_record: dict[str, Any], *, protocol_id: str, protocol_sha256: str, lexical_record_sha256: str
) -> P16TaskPacket:
    """Create the blind packet from a lexical record without exposing its labels."""

    occurrences: dict[tuple[str, str], int] = {}
    items: list[TaskPacketItem] = []
    for step in lexical_record["steps"]:
        key = (step["campaign_id"], step["technique_id"])
        occurrence = occurrences.get(key, 0) + 1
        occurrences[key] = occurrence
        excerpt = step["procedure_excerpt"]
        items.append(
            TaskPacketItem(
                item_id=_item_id(step, occurrence),
                campaign_id=step["campaign_id"],
                technique_id=step["technique_id"],
                procedure_excerpt=excerpt,
                procedure_excerpt_sha256=sha256_text(excerpt),
            )
        )
    return P16TaskPacket(
        schema_version=TASK_PACKET_SCHEMA_VERSION,
        protocol_id=protocol_id,
        protocol_sha256=protocol_sha256,
        source_record_sha256=lexical_record_sha256,
        items=items,
    )


def expected_labels(lexical_record: dict[str, Any]) -> dict[str, AdjudicationLabel]:
    """Map stable packet identifiers to the lexical screen labels for concordance checks."""

    occurrences: dict[tuple[str, str], int] = {}
    expected: dict[str, AdjudicationLabel] = {}
    for step in lexical_record["steps"]:
        key = (step["campaign_id"], step["technique_id"])
        occurrence = occurrences.get(key, 0) + 1
        occurrences[key] = occurrence
        try:
            expected[_item_id(step, occurrence)] = LEXICAL_TO_ADJUDICATION_LABEL[
                step["ordering_source"]
            ]
        except KeyError as error:
            raise ValueError(f"unrecognized lexical ordering source: {error.args[0]}") from error
    return expected


def _annotation_map(record: P16AnnotationRecord) -> dict[str, AnnotationDecision]:
    return {annotation.item_id: annotation for annotation in record.annotations}


def _validate_annotation_records(
    records: list[P16AnnotationRecord],
    *,
    protocol: P16AdjudicationProtocol,
    protocol_sha256: str,
    task_packet_sha256: str,
    item_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    seen_annotators: set[str] = set()
    for record in records:
        if record.protocol_id != protocol.protocol_id:
            errors.append(f"protocol_id:{record.annotator_id}")
        if record.protocol_sha256 != protocol_sha256:
            errors.append(f"protocol_sha256:{record.annotator_id}")
        if record.task_packet_sha256 != task_packet_sha256:
            errors.append(f"task_packet_sha256:{record.annotator_id}")
        if record.annotator_id in seen_annotators:
            errors.append(f"duplicate_annotator:{record.annotator_id}")
        seen_annotators.add(record.annotator_id)
        annotated_items = set(_annotation_map(record))
        if annotated_items != item_ids:
            errors.append(f"coverage:{record.annotator_id}")
    return errors


def _pairwise_agreement(records: list[P16AnnotationRecord], item_ids: list[str]) -> list[PairwiseAgreement]:
    agreements: list[PairwiseAgreement] = []
    for left, right in itertools.combinations(sorted(records, key=lambda record: record.annotator_id), 2):
        left_labels = _annotation_map(left)
        right_labels = _annotation_map(right)
        matching = sum(
            left_labels[item_id].label == right_labels[item_id].label for item_id in item_ids
        )
        agreements.append(
            PairwiseAgreement(
                annotator_a=left.annotator_id,
                annotator_b=right.annotator_id,
                exact_agreement=matching / len(item_ids),
                matching_items=matching,
                total_items=len(item_ids),
            )
        )
    return agreements


def _lexical_concordance(
    records: list[P16AnnotationRecord], expected: dict[str, AdjudicationLabel]
) -> float | None:
    if not records:
        return None
    decisions = [
        annotation
        for record in records
        for annotation in _annotation_map(record).values()
    ]
    if not decisions:
        return None
    matching = sum(
        annotation.label == expected[annotation.item_id] for annotation in decisions
    )
    return matching / len(decisions)


def evaluate_adjudication(
    *,
    protocol: P16AdjudicationProtocol,
    protocol_sha256: str,
    task_packet: P16TaskPacket,
    task_packet_sha256: str,
    lexical_record: dict[str, Any],
    lexical_record_sha256: str,
    records: list[P16AnnotationRecord],
) -> P16AdjudicationStatus:
    """Evaluate submitted records without turning unreviewed lexical labels into evidence."""

    if task_packet.protocol_id != protocol.protocol_id:
        raise ValueError("task packet references a different adjudication protocol")
    if task_packet.protocol_sha256 != protocol_sha256:
        raise ValueError("task packet protocol digest does not match the frozen protocol")
    if task_packet.source_record_sha256 != lexical_record_sha256:
        raise ValueError("task packet source digest does not match the lexical record")

    expected = expected_labels(lexical_record)
    item_ids = [item.item_id for item in task_packet.items]
    if set(item_ids) != set(expected):
        raise ValueError("task packet item set does not match the lexical record")
    if task_packet_sha256 != canonical_json_sha256(task_packet.model_dump(mode="json")):
        raise ValueError("task-packet digest does not match its content")

    validation_errors = _validate_annotation_records(
        records,
        protocol=protocol,
        protocol_sha256=protocol_sha256,
        task_packet_sha256=task_packet_sha256,
        item_ids=set(item_ids),
    )
    if validation_errors:
        raise ValueError(
            "invalid P16 adjudication records: " + ", ".join(sorted(validation_errors))
        )

    agreement = _pairwise_agreement(records, item_ids)
    concordance = _lexical_concordance(records, expected)
    reasons: list[str] = []
    if len(records) < protocol.minimum_annotators:
        reasons.append(f"requires_at_least_{protocol.minimum_annotators}_annotation_records")
    if len({record.annotator_id for record in records}) < protocol.minimum_annotators:
        reasons.append(f"requires_at_least_{protocol.minimum_annotators}_distinct_annotators")
    if records and not all(record.independence_attestation for record in records):
        reasons.append("all_annotation_records_must_attest_independence")
    if len(records) >= 2 and any(
        item.exact_agreement < protocol.minimum_pairwise_exact_agreement for item in agreement
    ):
        reasons.append("pairwise_exact_agreement_below_protocol_threshold")
    if records and protocol.require_lexical_concordance and concordance != 1.0:
        reasons.append("human_labels_do_not_fully_confirm_the_lexical_screen")

    status = "qualified" if not reasons else ("pending" if not records else "not_qualified")
    return P16AdjudicationStatus(
        schema_version=STATUS_SCHEMA_VERSION,
        claim_id=protocol.claim_id,
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol_sha256,
        task_packet_sha256=task_packet_sha256,
        lexical_record_sha256=lexical_record_sha256,
        lexical_item_count=len(item_ids),
        annotation_record_count=len(records),
        distinct_annotator_count=len({record.annotator_id for record in records}),
        all_records_attest_independence=bool(records) and all(
            record.independence_attestation for record in records
        ),
        pairwise_agreement=agreement,
        lexical_concordance=concordance,
        status=status,
        paper_eligible=status == "qualified",
        reasons=reasons,
    )


def load_annotation_records(records_directory: Path) -> list[P16AnnotationRecord]:
    """Load every submitted JSON record; malformed input is a hard error, never skipped."""

    if not records_directory.exists():
        return []
    records: list[P16AnnotationRecord] = []
    for path in sorted(records_directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.append(P16AnnotationRecord.model_validate(payload))
    return records


def validate_opaque_annotator_identifier(identifier: str) -> bool:
    """Expose the privacy-preserving identifier check to protocol tests and tools."""

    return bool(re.fullmatch(r"annotator-[a-f0-9]{8,64}", identifier))
