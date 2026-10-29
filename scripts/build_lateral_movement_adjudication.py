#!/usr/bin/env python3
"""Build the P16 blinded annotation packet and evaluate submitted human records.

This command does not manufacture an adjudication.  With the current empty records directory
it writes a `pending` status, which deliberately keeps STICKS-P16 out of the paper-ready
claim set.  It can promote the existing P16 wording only after the frozen protocol's complete
independent annotation records are present.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from evaluation.lateral_movement_adjudication import (  # noqa: E402
    P16AdjudicationProtocol,
    build_task_packet,
    canonical_json_sha256,
    evaluate_adjudication,
    file_sha256,
    load_annotation_records,
)

DEFAULT_PROTOCOL = (
    PROJECT_ROOT
    / "release"
    / "experiments"
    / "lateral_movement_grounding"
    / "adjudication"
    / "protocol.v1.json"
)


def _within_project(relative_path: str) -> Path:
    path = (PROJECT_ROOT / relative_path).resolve()
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as error:
        raise ValueError(f"protocol path escapes the project root: {relative_path}") from error
    return path


def _load_protocol(path: Path) -> P16AdjudicationProtocol:
    return P16AdjudicationProtocol.model_validate_json(path.read_text(encoding="utf-8"))


def _annotation_template(
    *, protocol: P16AdjudicationProtocol, protocol_sha256: str, task_packet_sha256: str, packet: dict
) -> dict:
    """Emit a non-evidence template. It stays outside `records/` and is never parsed as data."""

    return {
        "_template": True,
        "instructions": (
            "Copy this file to records/<opaque-id>.json, replace the placeholders, and remove "
            "the _template and instructions fields. Do not add identity-bearing or free-form text."
        ),
        "schema_version": "1.0.0",
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol_sha256,
        "task_packet_sha256": task_packet_sha256,
        "annotator_id": "annotator-00000000",
        "independence_attestation": False,
        "annotations": [
            {
                "item_id": item["item_id"],
                "label": "REPLACE_WITH_PROTOCOL_LABEL",
                "rationale_codes": ["REPLACE_WITH_PROTOCOL_RATIONALE"],
                "evidence_spans": [{"start": 0, "end": 1}],
            }
            for item in packet["items"]
        ],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(protocol_path: Path) -> tuple[Path, Path, Path]:
    """Regenerate all deterministic P16 adjudication surfaces from one protocol file."""

    protocol = _load_protocol(protocol_path)
    protocol_sha256 = file_sha256(protocol_path)
    source_path = _within_project(protocol.source_record_path)
    lexical_record = json.loads(source_path.read_text(encoding="utf-8"))
    lexical_record_sha256 = file_sha256(source_path)
    task_packet = build_task_packet(
        lexical_record,
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol_sha256,
        lexical_record_sha256=lexical_record_sha256,
    )
    task_packet_payload = task_packet.model_dump(mode="json")
    task_packet_sha256 = canonical_json_sha256(task_packet_payload)

    packet_path = _within_project(protocol.task_packet_path)
    template_path = packet_path.with_name("annotation.template.v1.json")
    status_path = _within_project(protocol.status_path)
    records_path = _within_project(protocol.records_directory)
    _write_json(packet_path, task_packet_payload)
    _write_json(
        template_path,
        _annotation_template(
            protocol=protocol,
            protocol_sha256=protocol_sha256,
            task_packet_sha256=task_packet_sha256,
            packet=task_packet_payload,
        ),
    )

    records = load_annotation_records(records_path)
    status = evaluate_adjudication(
        protocol=protocol,
        protocol_sha256=protocol_sha256,
        task_packet=task_packet,
        task_packet_sha256=task_packet_sha256,
        lexical_record=lexical_record,
        lexical_record_sha256=lexical_record_sha256,
        records=records,
    )
    _write_json(status_path, status.model_dump(mode="json"))
    return packet_path, template_path, status_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args()

    packet, template, status = build(args.protocol.resolve())
    status_payload = json.loads(status.read_text(encoding="utf-8"))
    print(
        "[p16-adjudication] "
        f"packet={packet.relative_to(PROJECT_ROOT)} "
        f"template={template.relative_to(PROJECT_ROOT)} "
        f"status={status_payload['status']} "
        f"records={status_payload['annotation_record_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
