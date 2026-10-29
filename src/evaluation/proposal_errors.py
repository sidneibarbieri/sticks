"""Typed error for an unusable model proposal.

A proposal the model returns in an unusable shape is data about the model, not a fault in the
harness. Raising a specific type lets the collection loop record it as an invalid observation while
every other error still propagates.
"""

from __future__ import annotations


class MalformedProposalError(ValueError):
    """The model reply could not be parsed into a proposal."""
