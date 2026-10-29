from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from compilers.stix_campaign_compiler import compile_campaign


# The compiler reads kill-chain order from the bundle's own matrix, so a fixture without one
# is not a valid Enterprise bundle for ordering purposes.
def matrix_objects(*shortnames: str) -> list[dict]:
    tactics = [
        {
            "type": "x-mitre-tactic",
            "id": f"x-mitre-tactic--{shortname}",
            "x_mitre_shortname": shortname,
        }
        for shortname in shortnames
    ]
    matrix = {
        "type": "x-mitre-matrix",
        "id": "x-mitre-matrix--enterprise",
        "tactic_refs": [tactic["id"] for tactic in tactics],
    }
    return [*tactics, matrix]



def test_compiler_is_deterministic_and_preserves_uncertainty(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle = {
        "type": "bundle",
        "objects": [
            {
                "type": "campaign",
                "id": "campaign--1",
                "name": "Example",
                "external_references": [{"source_name": "mitre-attack", "external_id": "C9999"}],
            },
            {
                "type": "attack-pattern",
                "id": "attack-pattern--2",
                "name": "Discover",
                "external_references": [{"source_name": "mitre-attack", "external_id": "T1082"}],
                "kill_chain_phases": [
                    {"kill_chain_name": "mitre-attack", "phase_name": "discovery"}
                ],
                "x_mitre_platforms": ["Linux"],
            },
            {
                "type": "attack-pattern",
                "id": "attack-pattern--1",
                "name": "Initial Access",
                "external_references": [{"source_name": "mitre-attack", "external_id": "T1190"}],
                "kill_chain_phases": [
                    {"kill_chain_name": "mitre-attack", "phase_name": "initial-access"}
                ],
            },
            {
                "type": "relationship",
                "id": "relationship--2",
                "relationship_type": "uses",
                "source_ref": "campaign--1",
                "target_ref": "attack-pattern--2",
            },
            {
                "type": "relationship",
                "id": "relationship--1",
                "relationship_type": "uses",
                "source_ref": "campaign--1",
                "target_ref": "attack-pattern--1",
            },
            *matrix_objects("initial-access", "discovery"),
        ],
    }
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    first = compile_campaign(bundle_path, "C9999")
    second = compile_campaign(bundle_path, "C9999")

    assert [step.technique_id for step in first.steps] == ["T1190", "T1082"]
    assert [step.execution_domain for step in first.steps] == ["boundary", "target"]
    assert first.content_sha256 == second.content_sha256
    assert first.validate_hash()
    assert "do not encode a historical total order" in first.limitations[0]


def test_plan_hash_validation_does_not_repair_tampered_input(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "type": "bundle",
                "objects": [
                    {
                        "type": "campaign",
                        "id": "campaign--1",
                        "name": "Example",
                        "external_references": [
                            {"source_name": "mitre-attack", "external_id": "C9999"}
                        ],
                    },
                    {
                        "type": "attack-pattern",
                        "id": "attack-pattern--1",
                        "name": "Discover",
                        "external_references": [
                            {"source_name": "mitre-attack", "external_id": "T1082"}
                        ],
                    },
                    {
                        "type": "relationship",
                        "id": "relationship--1",
                        "relationship_type": "uses",
                        "source_ref": "campaign--1",
                        "target_ref": "attack-pattern--1",
                    },
                    *matrix_objects("discovery"),
                ],
            }
        ),
        encoding="utf-8",
    )
    plan = compile_campaign(bundle_path, "C9999")
    expected_hash = plan.content_sha256
    plan.campaign_name = "Tampered"

    assert not plan.validate_hash()
    assert not plan.validate_hash()
    assert plan.content_sha256 == expected_hash
