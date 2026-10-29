#!/usr/bin/env python3
"""Compile a published Attack Flow into source steps and measure what it supplies.

The complementarity claim between this work and Attack Flow is easy to assert and worth
demonstrating. A flow records a human-authored order between actions, which an ATT&CK campaign
object does not, so reading one replaces the deterministic ordering policy with a declared
order. A flow records no concrete procedure, no environment binding and no success criterion,
so everything the admission model decides is still decided here.

The measurement is the difference between the two orders and the catalog's reach over the
flow's techniques, both computed over a corpus file published by its maintainers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from adapters.attack_flow import action_edges, declared_order, load_attack_flow  # noqa: E402

FLOW = PROJECT_ROOT / "data" / "interop" / "equifax-breach.afb"
CATALOG = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"
OUTPUT = PROJECT_ROOT / "release" / "experiments" / "attack_flow_interop" / "flow.json"


def tactic_rank_order(technique_ids: list[str], bundle_path: Path) -> list[str]:
    """The order this work would choose without a flow: tactic rank, then technique id."""
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    objects = bundle["objects"]

    tactics_by_id = {obj["id"]: obj for obj in objects if obj.get("type") == "x-mitre-tactic"}
    matrix = next(obj for obj in objects if obj.get("type") == "x-mitre-matrix")
    ranks = {
        tactics_by_id[reference]["x_mitre_shortname"]: rank
        for rank, reference in enumerate(matrix["tactic_refs"])
    }

    phases: dict[str, list[str]] = {}
    for obj in objects:
        if obj.get("type") != "attack-pattern":
            continue
        for reference in obj.get("external_references", []):
            if reference.get("source_name") == "mitre-attack":
                phases[reference.get("external_id", "")] = [
                    phase["phase_name"]
                    for phase in obj.get("kill_chain_phases", [])
                    if phase.get("kill_chain_name") == "mitre-attack"
                ]

    def sort_key(technique_id: str) -> tuple[int, str]:
        names = phases.get(technique_id, [])
        rank = min((ranks.get(name, len(ranks)) for name in names), default=len(ranks))
        return rank, technique_id

    return sorted(technique_ids, key=sort_key)


def inversion_count(authored: list[str], policy: list[str]) -> int:
    """Pairs the two orders disagree about."""
    position = {technique_id: index for index, technique_id in enumerate(policy)}
    inversions = 0
    for left in range(len(authored)):
        for right in range(left + 1, len(authored)):
            if position[authored[left]] > position[authored[right]]:
                inversions += 1
    return inversions


def main() -> int:
    document = load_attack_flow(FLOW)
    ordered = declared_order(document)
    with_technique = [action for action in ordered if action.technique_id]
    authored = [action.technique_id for action in with_technique]

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["templates"]
    supported_techniques = {
        technique_id for template in catalog for technique_id in template["technique_ids"]
    }
    covered = [technique_id for technique_id in authored if technique_id in supported_techniques]

    policy_order = tactic_rank_order(authored, BUNDLE)
    inversions = inversion_count(authored, policy_order)
    pairs = len(authored) * (len(authored) - 1) // 2

    payload = {
        "question": (
            "Does a published Attack Flow compile into source steps, and what does it supply "
            "that an ATT&CK campaign object does not?"
        ),
        "flow": FLOW.name,
        "flow_schema": document.schema_version,
        "actions": len(document.actions),
        "actions_with_technique": len(with_technique),
        "declared_action_edges": len(action_edges(document)),
        "authored_order": authored,
        "policy_order": policy_order,
        "order_pairs": pairs,
        "order_inversions": inversions,
        "catalog_supported_techniques": len(covered),
        "catalog_supported_technique_ids": covered,
        "note": (
            "The flow supplies behaviour identity and an authored order. It supplies no "
            "concrete procedure, no environment binding and no success criterion, so admission "
            "still decides every executable commitment."
        ),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[attack-flow] wrote {OUTPUT.relative_to(PROJECT_ROOT)}")
    print(
        f"[attack-flow] {len(with_technique)} actions carry a technique, "
        f"{len(action_edges(document))} authored edges, "
        f"{inversions}/{pairs} ordered pairs disagree with the tactic-rank policy"
    )
    print(f"[attack-flow] the catalog reaches {len(covered)} of {len(authored)} flow techniques")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
