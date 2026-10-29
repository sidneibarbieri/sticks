"""Credential-gated lateral movement is CTI-grounded only on Windows/cloud, never Linux SSH.

The grounding is read from each lateral step's own procedure description, not from technique
co-occurrence. The property that matters for the backend decision is that no genuinely
CTI-grounded chain is realizable host-to-host between two Linux VMs, so a Linux fallback would
have to be labeled ordering_source=procedure_dependency rather than cti.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.lateral_movement_grounding import evaluate  # noqa: E402

RECORD = (
    PROJECT_ROOT
    / "release"
    / "experiments"
    / "lateral_movement_grounding"
    / "grounding.json"
)
PLANS_DIR = PROJECT_ROOT / "release" / "plans" / "enterprise"


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def _load_plans() -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(PLANS_DIR.glob("*.procedural-plan.json"))
    ]


def test_no_cti_grounded_chain_is_realizable_on_a_linux_host_to_host_backend():
    assert _record()["cti_grounded_linux_capable_steps"] == 0


def test_the_record_is_explicitly_a_lexical_screen_not_a_semantic_adjudication():
    record = _record()
    assert record["scientific_status"] == "unadjudicated_lexical_screen"
    assert record["classifier_version"] == "p16-lexical-screen-v1"
    assert record["adjudication_protocol_path"].endswith("adjudication/protocol.v1.json")


def test_every_grading_partitions_into_the_three_ordering_sources():
    record = _record()
    partition = (
        record["cti_grounded_steps"]
        + record["independent_mechanism_steps"]
        + record["ungrounded_cooccurrence_steps"]
    )
    assert partition == record["lateral_steps_examined"]


def test_every_linux_capable_step_is_ungrounded_or_independent_never_cti():
    for step in _record()["steps"]:
        if step["linux_capable"]:
            assert step["ordering_source"] in {
                "procedure_dependency",
                "independent_mechanism",
            }


def test_the_record_regenerates_from_the_pinned_plans():
    assert evaluate(_load_plans()).model_dump(mode="json") == _record()
