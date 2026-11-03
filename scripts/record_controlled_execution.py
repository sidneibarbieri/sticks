#!/usr/bin/env python3
"""Record one verified execution cell in a new comparison ledger."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.controlled_comparison import (  # noqa: E402
    ArmId,
    ControlledComparisonManifest,
    EvidenceReference,
    EvidenceRole,
    RunLedger,
    RunRecord,
    RunStatus,
)

EXECUTION_FILES = {
    EvidenceRole.admitted_plan: "admitted-plan.json",
    EvidenceRole.execution_semantic_bridge: "execution-semantic-bridge.json",
    EvidenceRole.execution_handoff: "execution-handoff.json",
    EvidenceRole.consumer_receipt: "consumer-receipt.json",
    EvidenceRole.independent_observation: "independent-observation.json",
}


def evidence_references(evidence_root: Path, cell_dir: Path) -> list[EvidenceReference]:
    root = evidence_root.resolve(strict=True)
    cell = cell_dir.resolve(strict=True)
    relative_cell = cell.relative_to(root)
    references = []
    for role, filename in EXECUTION_FILES.items():
        path = (cell / filename).resolve(strict=True)
        path.relative_to(root)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        references.append(
            EvidenceReference(path=str(relative_cell / filename), sha256=digest, role=role)
        )
    return references


def record_execution(
    manifest: ControlledComparisonManifest,
    ledger: RunLedger,
    evidence_root: Path,
    cell_dir: Path,
    campaign_id: str,
    seed: int,
) -> RunLedger:
    manifest.validate_collection_ready()
    ledger.validate_against(manifest)
    key = (campaign_id, ArmId.sticks_autosut_executed.value, seed)
    matches = [record for record in ledger.records if record.key() == key]
    if len(matches) != 1 or matches[0].status != RunStatus.planned:
        raise ValueError("execution cell must exist exactly once with planned status")
    completed = RunRecord(
        campaign_id=campaign_id,
        arm_id=ArmId.sticks_autosut_executed,
        seed=seed,
        status=RunStatus.succeeded,
        evidence=evidence_references(evidence_root, cell_dir),
    )
    updated = RunLedger(
        schema_version=ledger.schema_version,
        experiment_id=ledger.experiment_id,
        records=[completed if record.key() == key else record for record in ledger.records],
    )
    updated.validate_against(manifest)
    updated.validate_evidence(evidence_root)
    updated.validate_execution_evidence(evidence_root)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--cell-dir", type=Path, required=True)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-ledger", type=Path, required=True)
    args = parser.parse_args()
    if args.output_ledger.resolve() == args.ledger.resolve():
        raise ValueError("output ledger must differ from the frozen input ledger")
    manifest = ControlledComparisonManifest.model_validate_json(args.manifest.read_text())
    ledger = RunLedger.model_validate_json(args.ledger.read_text())
    updated = record_execution(
        manifest, ledger, args.evidence_root, args.cell_dir, args.campaign, args.seed
    )
    with args.output_ledger.open("x", encoding="utf-8") as output:
        output.write(updated.model_dump_json(indent=2) + "\n")
    print(f"recorded {args.campaign}/seed{args.seed} in {args.output_ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
