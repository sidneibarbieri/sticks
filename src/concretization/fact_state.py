"""Typed fact states.

Admissibility is decided against a set of facts, but three different fact sets carry three
different meanings, and a result computed against one must not be reported as if it held
against another. Representing all three as a bare set of strings makes that substitution
invisible; carrying the scope inside the value makes it explicit at every call site.

  hypothetical  the declared initial facts plus every fact the catalog can produce.
                Over-approximates by construction: it answers whether a template could ever
                apply, which is a property of the catalog, not of a campaign.
  initial       the environment's declared initial facts, before any step runs.
  sequential    the facts holding when a step is reached: the initial facts plus what the
                preceding committed steps produced. This is the state the pipeline commits
                against, and the only one whose multiplicity means an alternative existed
                at execution time.

``require`` converts a state to a plain fact set only after asserting the expected scope,
so an analysis that needs sequential facts cannot silently consume hypothetical ones.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AdmissibilityScope(str, Enum):
    hypothetical = "hypothetical"
    initial = "initial"
    sequential = "sequential"


class FactState(BaseModel):
    """A set of facts together with the scope that gives it meaning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: AdmissibilityScope
    facts: frozenset[str]
    # For sequential states, the step whose arrival this state describes.
    reached_technique_id: str | None = Field(default=None)

    def require(self, expected: AdmissibilityScope) -> frozenset[str]:
        """Return the facts, refusing to serve them under the wrong scope."""
        if self.scope is not expected:
            raise ValueError(
                f"expected a {expected.value} fact state but received {self.scope.value}; "
                "convert explicitly rather than reinterpreting the scope"
            )
        return self.facts
