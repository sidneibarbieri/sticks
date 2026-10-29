from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from adapters.attack_flow import (
    action_edges,
    declared_order,
    load_attack_flow,
    parse_attack_flow,
)

FLOW = PROJECT_ROOT / "data" / "interop" / "equifax-breach.afb"


def _node(node_id, instance, properties=None, **extra):
    payload = {"id": node_id, "instance": instance}
    if properties is not None:
        payload["properties"] = properties
    payload.update(extra)
    return payload


def _minimal_flow():
    return {
        "schema": "attack_flow_v2",
        "objects": [
            _node(
                "action",
                "act-1",
                [["name", "First"], ["ttp", [["tactic", "TA0001"], ["technique", "T1190"]]]],
                anchors={"0": "anch-1"},
            ),
            _node(
                "action",
                "act-2",
                [["name", "Second"], ["ttp", [["tactic", "TA0002"], ["technique", "T1059"]]]],
                anchors={"0": "anch-2"},
            ),
            _node("horizontal_anchor", "anch-1", latches=["latch-1"]),
            _node("horizontal_anchor", "anch-2", latches=["latch-2"]),
            _node("generic_latch", "latch-1"),
            _node("generic_latch", "latch-2"),
            _node("dynamic_line", "line-1", source="latch-1", target="latch-2"),
        ],
    }


def test_actions_carry_technique_and_tactic():
    document = parse_attack_flow(_minimal_flow())
    assert [action.technique_id for action in document.actions] == ["T1190", "T1059"]
    assert document.actions[0].tactic_id == "TA0001"


def test_an_edge_resolves_through_latch_and_anchor():
    document = parse_attack_flow(_minimal_flow())
    assert [(edge.source_id, edge.target_id) for edge in document.edges] == [("act-1", "act-2")]


def test_intermediate_nodes_are_contracted_into_action_edges():
    payload = _minimal_flow()
    payload["objects"] += [
        _node("condition", "cond-1", anchors={"0": "anch-3", "1": "anch-4"}),
        _node("horizontal_anchor", "anch-3", latches=["latch-3"]),
        _node("horizontal_anchor", "anch-4", latches=["latch-4"]),
        _node("generic_latch", "latch-3"),
        _node("generic_latch", "latch-4"),
        _node("action", "act-3", [["name", "Third"]], anchors={"0": "anch-5"}),
        _node("horizontal_anchor", "anch-5", latches=["latch-5"]),
        _node("generic_latch", "latch-5"),
        _node("dynamic_line", "line-2", source="latch-2", target="latch-3"),
        _node("dynamic_line", "line-3", source="latch-4", target="latch-5"),
    ]
    document = parse_attack_flow(payload)
    contracted = {(edge.source_id, edge.target_id) for edge in action_edges(document)}
    assert ("act-2", "act-3") in contracted


def test_declared_order_follows_the_authored_edges():
    document = parse_attack_flow(_minimal_flow())
    assert [action.action_id for action in declared_order(document)] == ["act-1", "act-2"]


def test_an_action_without_a_technique_is_kept_but_flagged():
    payload = _minimal_flow()
    payload["objects"].append(_node("action", "act-9", [["name", "Untyped"]], anchors={}))
    document = parse_attack_flow(payload)
    assert len(document.actions) == 3
    assert len(document.actions_with_technique()) == 2


def test_the_published_flow_parses_and_orders_reconnaissance_first():
    document = load_attack_flow(FLOW)
    ordered = [action.technique_id for action in declared_order(document) if action.technique_id]
    assert len(ordered) == 12
    assert ordered[0] == "T1595.002"
    assert ordered[1] == "T1190"


def test_the_released_interop_record_matches_the_flow():
    payload = json.loads(
        (PROJECT_ROOT / "release/experiments/attack_flow_interop/flow.json").read_text(
            encoding="utf-8"
        )
    )
    document = load_attack_flow(FLOW)
    assert payload["actions_with_technique"] == len(document.actions_with_technique())
    assert payload["declared_action_edges"] == len(action_edges(document))
    assert 0 < payload["order_inversions"] < payload["order_pairs"]
