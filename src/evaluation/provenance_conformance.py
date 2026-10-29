"""Conformance audit for the provenance attribution rules.

Verifies that every binding source observed in the campaign catalogs is explicitly covered
by the frozen taxonomy, so no value is classified by accident. ``classify_binding`` is
fail-closed and raises on an unrecognized source; this audit runs first so an uncovered
source is reported rather than raising mid-analysis.

Scope: this establishes classifier coverage over the evaluated data. It does not validate
that the source-to-class rules are semantically correct -- that a ``sut`` binding is truly
environment-determined, for example -- which remains a separate human-validation task.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from .provenance import (
    BINDING_SOURCE_CLASSES,
    TAXONOMY_VERSION,
    BindingProvenance,
    classify_binding,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceCoverage(StrictModel):
    taxonomy_version: str
    # Each observed source mapped to the class it received (covered sources only).
    observed_sources: dict[str, BindingProvenance]
    # Observed sources absent from the taxonomy (must be empty to be conformant).
    unknown_sources: list[str]
    conformant: bool


def audit_source_coverage(
    catalog_bindings: list[dict[str, Any]],
) -> SourceCoverage:
    observed: dict[str, BindingProvenance] = {}
    unknown: list[str] = []
    for binding in catalog_bindings:
        source = binding["source"]
        if source in BINDING_SOURCE_CLASSES:
            observed[source] = classify_binding(source)
        elif source not in unknown:
            unknown.append(source)
    return SourceCoverage(
        taxonomy_version=TAXONOMY_VERSION,
        observed_sources=dict(sorted(observed.items())),
        unknown_sources=sorted(unknown),
        conformant=not unknown,
    )
