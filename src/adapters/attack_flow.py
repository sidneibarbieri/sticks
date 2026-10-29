"""Read a published Attack Flow and expose it as ordered technique steps.

Attack Flow records what an incident did and, unlike an ATT&CK campaign object, it records a
human-authored order between actions. It does not record the concrete procedure, the
environment binding, or a success criterion, which is the boundary the admission model
covers. Reading a flow therefore replaces one thing this work otherwise supplies by policy,
the source ordering, and leaves the rest of the contract to be admitted as usual.

The builder format stores node properties as name/value pairs and joins nodes through a
latch and anchor indirection rather than by direct reference, so resolving an edge means
walking line to latch to anchor to node.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from contracts.flow_structure import ConditionalExit as FlowBranch

ACTION_NODE = "action"
EDGE_NODE = "dynamic_line"
ANCHOR_NODES = ("horizontal_anchor", "vertical_anchor")


class FlowAction(BaseModel):
    """One adversary action the flow author recorded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str
    name: str
    technique_id: str | None
    tactic_id: str | None
    description: str


class FlowEdge(BaseModel):
    """A declared causal edge between two flow nodes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    target_id: str


class FlowCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_id: str
    pattern: str
    description: str = ""
    pattern_type: str | None = None
    pattern_version: str | None = None


class FlowOperator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operator_id: str
    kind: Literal["AND", "OR"]


class AttackFlowDocument(BaseModel):
    """Actions, precedence, and authored conditional exits in a flow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    actions: list[FlowAction]
    edges: list[FlowEdge]
    conditions: list[FlowCondition] = []
    branches: list[FlowBranch] = []
    operators: list[FlowOperator] = []

    def actions_with_technique(self) -> list[FlowAction]:
        return [action for action in self.actions if action.technique_id]


def _properties(node: Mapping[str, object]) -> dict[str, object]:
    """Flatten the builder's name/value pair list into a mapping."""
    pairs = node.get("properties") or []
    return {str(name): value for name, value in pairs}


def _technique_and_tactic(node: Mapping[str, object]) -> tuple[str | None, str | None]:
    ttp = _properties(node).get("ttp")
    if not isinstance(ttp, Sequence):
        return None, None
    fields = {str(name): value for name, value in ttp}
    technique = fields.get("technique")
    tactic = fields.get("tactic")
    return (str(technique) if technique else None, str(tactic) if tactic else None)


def _anchor_owner(objects: Sequence[Mapping[str, object]]) -> dict[str, str]:
    """Map each anchor instance to the node that owns it."""
    owner: dict[str, str] = {}
    for node in objects:
        for anchor_instance in (node.get("anchors") or {}).values():
            owner[str(anchor_instance)] = str(node["instance"])
    return owner


def _latch_anchor(objects: Sequence[Mapping[str, object]]) -> dict[str, str]:
    """Map each latch instance to the anchor holding it."""
    holder: dict[str, str] = {}
    for node in objects:
        if node.get("id") not in ANCHOR_NODES:
            continue
        for latch_instance in node.get("latches") or []:
            holder[str(latch_instance)] = str(node["instance"])
    return holder


def parse_attack_flow(payload: Mapping[str, object]) -> AttackFlowDocument:
    objects = list(payload["objects"])
    owner = _anchor_owner(objects)
    holder = _latch_anchor(objects)
    nodes_by_id = {str(node["instance"]): node for node in objects}
    anchor_labels = {
        str(anchor_instance): (str(node["instance"]), str(label))
        for node in objects
        for label, anchor_instance in (node.get("anchors") or {}).items()
    }

    actions = []
    for node in objects:
        if node.get("id") != ACTION_NODE:
            continue
        technique, tactic = _technique_and_tactic(node)
        fields = _properties(node)
        actions.append(
            FlowAction(
                action_id=str(node["instance"]),
                name=str(fields.get("name") or ""),
                technique_id=technique,
                tactic_id=tactic,
                description=str(fields.get("description") or ""),
            )
        )

    conditions = [
        FlowCondition(
            condition_id=str(node["instance"]),
            pattern=str(_properties(node).get("pattern") or ""),
            description=str(_properties(node).get("description") or ""),
            pattern_type=_properties(node).get("pattern_type"),
            pattern_version=_properties(node).get("pattern_version"),
        )
        for node in objects
        if node.get("id") == "condition"
    ]
    operators = [
        FlowOperator(
            operator_id=str(node["instance"]),
            kind=_properties(node)["operator"],
        )
        for node in objects
        if node.get("id") in ("AND_operator", "OR_operator")
    ]
    edges = []
    branches = []
    for node in objects:
        if node.get("id") != EDGE_NODE:
            continue
        source = owner.get(holder.get(str(node.get("source")), ""), "")
        target = owner.get(holder.get(str(node.get("target")), ""), "")
        if source and target:
            edges.append(FlowEdge(source_id=source, target_id=target))
            if nodes_by_id[source].get("id") == "condition":
                source_anchor = holder[str(node["source"])]
                label = anchor_labels[source_anchor][1]
                if label in ("branch:True", "branch:False"):
                    branches.append(
                        FlowBranch(
                            condition_id=source,
                            target_id=target,
                            when_true=label == "branch:True",
                        )
                    )

    return AttackFlowDocument(
        schema_version=str(payload["schema"]),
        actions=actions,
        edges=edges,
        conditions=conditions,
        branches=branches,
        operators=operators,
    )


def load_attack_flow(path: Path) -> AttackFlowDocument:
    return parse_attack_flow(json.loads(path.read_text(encoding="utf-8")))


def action_edges(document: AttackFlowDocument) -> list[FlowEdge]:
    """Action-to-action edges, contracting the condition and operator nodes between them.

    A flow rarely joins two actions directly. It routes them through condition and operator
    nodes, so reading only direct edges recovers almost no order. Contracting those nodes
    keeps the order the author drew without inventing one.
    """
    action_ids = {action.action_id for action in document.actions}
    successors: dict[str, set[str]] = {}
    for edge in document.edges:
        successors.setdefault(edge.source_id, set()).add(edge.target_id)

    contracted: set[tuple[str, str]] = set()
    for source in action_ids:
        pending = list(successors.get(source, ()))
        seen: set[str] = set()
        while pending:
            node_id = pending.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            if node_id in action_ids:
                contracted.add((source, node_id))
            else:
                pending.extend(successors.get(node_id, ()))
    return [FlowEdge(source_id=source, target_id=target) for source, target in sorted(contracted)]


def declared_order(document: AttackFlowDocument) -> list[FlowAction]:
    """Analysis-only action ordering; conditional exits may both appear.

    Ties are broken by action identifier so the result is reproducible. Actions the edges do
    not reach keep their document position rather than being dropped.
    """
    by_id = {action.action_id: action for action in document.actions}
    incoming: dict[str, set[str]] = {action_id: set() for action_id in by_id}
    for edge in action_edges(document):
        incoming[edge.target_id].add(edge.source_id)

    ordered: list[FlowAction] = []
    placed: set[str] = set()
    remaining = dict(incoming)
    while remaining:
        ready = sorted(
            action_id for action_id, sources in remaining.items() if not sources - placed
        )
        if not ready:
            ready = sorted(remaining)
        for action_id in ready:
            ordered.append(by_id[action_id])
            placed.add(action_id)
            remaining.pop(action_id)
    return ordered
