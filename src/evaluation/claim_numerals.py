"""Bind every number a claim states to a value its evidence can still produce.

A registered property carries numbers in prose. Nothing in the evidence chain forces those
numbers to agree with the records they summarise, so re-pinning the corpus can leave a
property asserting a population its evidence no longer contains. That failure is silent:
the chain stays complete, the hashes stay valid, and only the prose is wrong.

This module closes that gap. Every numeric literal in a property's prose must be
renderable from that property's own evidence, either directly from a stored value, a list
length, or a rate, or through a reduction the property declares. A number that is declared
experiment configuration rather than a measurement is exempted explicitly and carries its
justification in the ledger, so it stays visible instead of passing unnoticed.

Identifier tokens such as technique, campaign, and property identifiers are not
measurements and are removed before literals are collected.

The module deliberately knows nothing about the claim model, so the ledger can depend on
it without the dependency running the other way.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

IDENTIFIER_PATTERN = re.compile(
    r"\b(?:[TCGSM]\d{4}(?:\.\d{3})?|CVE-\d{4}-\d+|(?:STICKS-)?[PB]\d{2})\b"
)
NUMERIC_LITERAL_PATTERN = re.compile(r"\d+(?:\.\d+)?")

PERCENT_DECIMAL_PLACES = (0, 1)
DECIMAL_PLACES = (1, 2, 3)


class Reduction(str, Enum):
    """How a declared quantity is computed from its evidence documents."""

    total = "total"
    document_count = "document_count"


class Accessor(str, Enum):
    """What a reduction reads at each declared field path."""

    value = "value"
    length = "length"


class Rendering(str, Enum):
    """How a resolved value is written in prose."""

    integer = "integer"
    decimal = "decimal"
    percent = "percent"


class ClaimQuantity(BaseModel):
    """One number in a claim's prose and the evidence reduction that produces it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    literal: str
    reduction: Reduction
    evidence_paths: list[str]
    field_paths: list[str] = Field(default_factory=list)
    accessor: Accessor = Accessor.value
    rendering: Rendering = Rendering.integer
    decimals: int = 1

    @model_validator(mode="after")
    def check_reduction_arguments(self) -> ClaimQuantity:
        if not self.evidence_paths:
            raise ValueError("a quantity must name at least one evidence document")
        if self.reduction is Reduction.total and not self.field_paths:
            raise ValueError("reduction total requires at least one field path")
        if self.reduction is Reduction.document_count and self.field_paths:
            raise ValueError("reduction document_count takes no field paths")
        return self


class NumericExemption(BaseModel):
    """A number the claim states that is declared configuration, not a measurement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    literal: str
    justification: str


class NumeralAudit(BaseModel):
    """Result of checking one claim's prose numbers against its evidence."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    unbound_literals: list[str]
    quantity_mismatches: list[str]
    unused_declarations: list[str]
    clean: bool


def prose_literals(prose: Iterable[str | None]) -> set[str]:
    """Collect the numeric literals a claim states, ignoring identifier tokens."""
    literals: set[str] = set()
    for text in prose:
        if text:
            literals.update(NUMERIC_LITERAL_PATTERN.findall(IDENTIFIER_PATTERN.sub(" ", text)))
    return literals


def _renderings(value: object) -> set[str]:
    """Every way a single scalar could legitimately appear in prose."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return set()
    if isinstance(value, int):
        return {str(value)}
    written = {f"{value:.{places}f}" for places in DECIMAL_PLACES}
    if value.is_integer():
        written.add(str(int(value)))
    if 0.0 <= value <= 1.0:
        written.update(f"{value * 100:.{places}f}" for places in PERCENT_DECIMAL_PLACES)
    return written


def renderable_values(node: object) -> set[str]:
    """Every literal the evidence document can produce, including list lengths."""
    written: set[str] = set()
    if isinstance(node, dict):
        for child in node.values():
            written |= renderable_values(child)
    elif isinstance(node, list):
        written |= _renderings(len(node))
        for child in node:
            written |= renderable_values(child)
    else:
        written |= _renderings(node)
    return written


def read_field(document: object, field_path: str) -> object:
    """Follow a dotted path into a loaded JSON document."""
    node = document
    for segment in field_path.split("."):
        node = node[segment]
    return node


def render_value(value: float, rendering: Rendering, decimals: int) -> str:
    if rendering is Rendering.integer:
        return str(int(value))
    if rendering is Rendering.percent:
        return f"{value * 100:.{decimals}f}"
    return f"{value:.{decimals}f}"


def _load_json_documents(project_root: Path, relative_paths: Sequence[str]) -> list[object]:
    return [
        json.loads((project_root / relative_path).read_text(encoding="utf-8"))
        for relative_path in relative_paths
        if relative_path.endswith(".json")
    ]


def _measure(document: object, field_path: str, accessor: Accessor) -> float:
    target = read_field(document, field_path)
    if accessor is Accessor.length:
        return len(target)
    return target


def resolve_quantity(quantity: ClaimQuantity, project_root: Path) -> str:
    """Compute the literal a declared quantity currently renders to."""
    documents = _load_json_documents(project_root, quantity.evidence_paths)
    if quantity.reduction is Reduction.document_count:
        return str(len(documents))
    total = sum(
        _measure(document, field_path, quantity.accessor)
        for document in documents
        for field_path in quantity.field_paths
    )
    return render_value(total, quantity.rendering, quantity.decimals)


def audit_numerals(
    claim_id: str,
    prose: Sequence[str | None],
    quantities: Sequence[ClaimQuantity],
    exemptions: Sequence[NumericExemption],
    evidence_paths: Sequence[str],
    project_root: Path,
) -> NumeralAudit:
    """Check that every number the claim states is still produced by its evidence."""
    stated = prose_literals(prose)

    available: set[str] = set()
    for document in _load_json_documents(project_root, evidence_paths):
        available |= renderable_values(document)

    chain = set(evidence_paths)
    mismatches: list[str] = []
    resolved_literals: set[str] = set()
    for quantity in quantities:
        outside_chain = sorted(set(quantity.evidence_paths) - chain)
        if outside_chain:
            mismatches.append(
                f"{quantity.literal} reads documents outside the claim's evidence chain: "
                f"{', '.join(outside_chain)}"
            )
            continue
        resolved = resolve_quantity(quantity, project_root)
        if resolved == quantity.literal:
            resolved_literals.add(quantity.literal)
        else:
            mismatches.append(f"{quantity.literal} resolves to {resolved}")

    exempted = {exemption.literal for exemption in exemptions}
    declared = resolved_literals | exempted
    unused = sorted(declared - stated, key=float)
    unbound = sorted(stated - available - declared, key=float)

    return NumeralAudit(
        claim_id=claim_id,
        unbound_literals=unbound,
        quantity_mismatches=mismatches,
        unused_declarations=unused,
        clean=not (unbound or mismatches or unused),
    )
