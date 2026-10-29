"""P16 cannot turn a lexical screen into a paper claim without adjudication evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.lateral_movement_adjudication import (  # noqa: E402
    AdjudicationLabel,
    AnnotationDecision,
    P16AdjudicationProtocol,
    P16AnnotationRecord,
    RationaleCode,
    TextSpan,
    build_task_packet,
    canonical_json_sha256,
    evaluate_adjudication,
    expected_labels,
    file_sha256,
)

ADJUDICATION_DIR = (
    PROJECT_ROOT
    / "release"
    / "experiments"
    / "lateral_movement_grounding"
    / "adjudication"
)
PROTOCOL_PATH = ADJUDICATION_DIR / "protocol.v1.json"
GROUNDING_PATH = (
    PROJECT_ROOT
    / "release"
    / "experiments"
    / "lateral_movement_grounding"
    / "grounding.json"
)


def _inputs():
    protocol = P16AdjudicationProtocol.model_validate_json(
        PROTOCOL_PATH.read_text(encoding="utf-8")
    )
    lexical = json.loads(GROUNDING_PATH.read_text(encoding="utf-8"))
    protocol_digest = file_sha256(PROTOCOL_PATH)
    lexical_digest = file_sha256(GROUNDING_PATH)
    packet = build_task_packet(
        lexical,
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol_digest,
        lexical_record_sha256=lexical_digest,
    )
    packet_digest = canonical_json_sha256(packet.model_dump(mode="json"))
    return protocol, lexical, protocol_digest, lexical_digest, packet, packet_digest


def _annotation_record(identifier: str, *, alter_first_label: bool = False) -> P16AnnotationRecord:
    protocol, lexical, protocol_digest, _, packet, packet_digest = _inputs()
    labels = expected_labels(lexical)
    decisions: list[AnnotationDecision] = []
    altered = False
    for item in packet.items:
        label = labels[item.item_id]
        if alter_first_label and not altered and label is not AdjudicationLabel.insufficient_evidence:
            label = AdjudicationLabel.insufficient_evidence
            altered = True
        rationale = {
            AdjudicationLabel.credential_reuse: RationaleCode.explicit_credential_reuse,
            AdjudicationLabel.independent_mechanism: RationaleCode.explicit_independent_mechanism,
            AdjudicationLabel.insufficient_evidence: RationaleCode.insufficient_textual_link,
        }[label]
        spans = []
        if label is not AdjudicationLabel.insufficient_evidence:
            spans = [TextSpan(start=0, end=1)]
        decisions.append(
            AnnotationDecision(
                item_id=item.item_id,
                label=label,
                rationale_codes=[rationale],
                evidence_spans=spans,
            )
        )
    return P16AnnotationRecord(
        schema_version="1.0.0",
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol_digest,
        task_packet_sha256=packet_digest,
        annotator_id=identifier,
        independence_attestation=True,
        annotations=decisions,
    )


def _evaluate(records: list[P16AnnotationRecord]):
    protocol, lexical, protocol_digest, lexical_digest, packet, packet_digest = _inputs()
    return evaluate_adjudication(
        protocol=protocol,
        protocol_sha256=protocol_digest,
        task_packet=packet,
        task_packet_sha256=packet_digest,
        lexical_record=lexical,
        lexical_record_sha256=lexical_digest,
        records=records,
    )


def test_task_packet_is_blinded_to_the_lexical_labels():
    _, _, _, _, packet, _ = _inputs()
    rendered = packet.model_dump_json()
    assert "ordering_source" not in rendered
    assert "credential_reuse" not in rendered
    assert "independent_mechanism" not in rendered


def test_no_records_is_pending_and_not_paper_eligible():
    status = _evaluate([])
    assert status.status == "pending"
    assert status.paper_eligible is False
    assert status.reasons == ["requires_at_least_2_annotation_records", "requires_at_least_2_distinct_annotators"]


def test_two_complete_independent_records_that_confirm_the_screen_qualify():
    status = _evaluate(
        [
            _annotation_record("annotator-0a1b2c3d"),
            _annotation_record("annotator-4e5f6a7b"),
        ]
    )
    assert status.status == "qualified"
    assert status.paper_eligible is True
    assert status.lexical_concordance == 1.0
    assert status.pairwise_agreement[0].exact_agreement == 1.0


def test_two_agreeing_records_that_disagree_with_the_lexical_screen_do_not_promote_p16():
    status = _evaluate(
        [
            _annotation_record("annotator-0a1b2c3d", alter_first_label=True),
            _annotation_record("annotator-4e5f6a7b", alter_first_label=True),
        ]
    )
    assert status.status == "not_qualified"
    assert status.paper_eligible is False
    assert "human_labels_do_not_fully_confirm_the_lexical_screen" in status.reasons


def test_duplicate_opaque_identity_is_rejected_even_if_two_files_exist():
    with pytest.raises(ValueError, match="duplicate_annotator"):
        _evaluate(
            [
                _annotation_record("annotator-0a1b2c3d"),
                _annotation_record("annotator-0a1b2c3d"),
            ]
        )


def test_affirmative_label_requires_a_source_span():
    with pytest.raises(ValueError, match="affirmative labels require"):
        AnnotationDecision(
            item_id="C0002:T1550.002:01",
            label=AdjudicationLabel.credential_reuse,
            rationale_codes=[RationaleCode.explicit_credential_reuse],
            evidence_spans=[],
        )
