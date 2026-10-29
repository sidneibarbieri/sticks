"""The unconstrained-reconstruction divergence metric and its frozen record.

Without a catalog or verifier, independent proposers commit different executable procedures
for the same CTI step. The metric counts that divergence at the decision level, and this test
pins both its behavior on controlled inputs and the shape of the frozen corpus record.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.unconstrained_reconstruction import (  # noqa: E402
    Reconstruction,
    aggregate,
    step_divergence,
)

CORPUS = (
    PROJECT_ROOT / "release" / "experiments" / "unconstrained_divergence" / "corpus.json"
)


def _reconstruction(proposer: str, mechanism: str, target: str, url: str) -> Reconstruction:
    return Reconstruction(
        technique_id="T1105",
        proposer=proposer,
        mechanism=mechanism,
        target=target,
        command=f"download {url}",
        parameters={"url": url},
    )


def test_identical_reconstructions_do_not_diverge():
    same = [
        _reconstruction("a", "curl-download", "target.primary", "http://lab/x"),
        _reconstruction("b", "curl-download", "target.primary", "http://lab/x"),
        _reconstruction("c", "curl-download", "target.primary", "http://lab/x"),
    ]
    divergence = step_divergence(same)
    assert divergence.distinct_executable_decisions == 1
    assert divergence.decision_agreement_rate == 1.0


def test_surface_differences_do_not_count_as_divergence():
    # Same decision, only whitespace and case differ: the decision must be treated as identical.
    variants = [
        _reconstruction("a", "curl-download", "target.primary", "http://lab/x"),
        _reconstruction("b", "Curl-Download ", " target.primary", "http://lab/x"),
    ]
    assert step_divergence(variants).distinct_executable_decisions == 1


def test_different_mechanisms_or_values_diverge():
    different = [
        _reconstruction("a", "curl-download", "target.primary", "http://lab/x"),
        _reconstruction("b", "wget-download", "target.primary", "http://lab/x"),
        _reconstruction("c", "curl-download", "target.primary", "http://other/y"),
    ]
    divergence = step_divergence(different)
    assert divergence.distinct_executable_decisions == 3
    assert divergence.decision_agreement_rate == 0.0


def test_frozen_corpus_reports_divergence_against_the_finite_domain_arm():
    record = json.loads(CORPUS.read_text(encoding="utf-8"))
    # Every step keeps its full panel of proposers.
    assert record["proposers_per_step"] >= 2
    assert all(
        step["reconstruction_count"] == record["proposers_per_step"]
        for step in record["per_step"]
    )
    # The finite-domain arm converges to one committed execution; the unconstrained arm does
    # not converge on any step.
    assert record["steps_with_full_decision_agreement"] == 0
    assert record["mean_distinct_executable_decisions"] > 1.0


def test_aggregate_rejects_an_empty_corpus():
    try:
        aggregate([], note="", campaigns=0)
    except ValueError:
        return
    raise AssertionError("aggregate must reject an empty corpus rather than report zeros")
