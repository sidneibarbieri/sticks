from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.behavioral_substitution import (  # noqa: E402
    Classification,
    DimensionResult,
    Substrate,
    TemplateObservation,
    classify_observations,
    evaluate_step,
    unavailable_observation,
)


def _obs(template_id, *, exit_code=0, satisfied=True, effects=("payload:staged",),
         artifacts=("dst",), telemetry=DimensionResult.observed,
         detection=DimensionResult.observed) -> TemplateObservation:
    return TemplateObservation(
        template_id=template_id,
        substrate=Substrate.lab,
        executed=True,
        exit_code=exit_code,
        evidence_predicate_satisfied=satisfied,
        produced_effects=list(effects),
        host_artifacts=list(artifacts),
        telemetry=telemetry,
        detection=detection,
    )


def test_unavailable_substrate_is_inconclusive():
    observations = [unavailable_observation("a"), unavailable_observation("b")]
    classification, _ = classify_observations(observations)
    assert classification is Classification.inconclusive


def test_fully_instrumented_equal_is_behaviorally_equivalent():
    classification, _ = classify_observations([_obs("a"), _obs("b")])
    assert classification is Classification.behaviorally_equivalent


def test_differing_observed_dimension_is_observably_distinct():
    classification, _ = classify_observations(
        [_obs("a", effects=("payload:staged",)), _obs("b", effects=("payload:dropped",))]
    )
    assert classification is Classification.observably_distinct


def test_uninstrumented_telemetry_keeps_equal_case_inconclusive():
    # Equal on observed dimensions but telemetry/detection not captured -> not full equivalence.
    classification, rationale = classify_observations(
        [
            _obs("a", telemetry=DimensionResult.not_instrumented,
                 detection=DimensionResult.not_instrumented),
            _obs("b", telemetry=DimensionResult.not_instrumented,
                 detection=DimensionResult.not_instrumented),
        ]
    )
    assert classification is Classification.inconclusive
    assert "not instrumented" in rationale


def test_single_executed_alternative_is_inconclusive():
    classification, _ = classify_observations([_obs("a"), unavailable_observation("b")])
    assert classification is Classification.inconclusive


def test_evaluate_step_uses_injected_observer():
    step = evaluate_step(
        campaign_id="C0045",
        technique_id="T1105",
        execution_domain="boundary",
        admissible_template_ids=["transfer-benign-payload", "transfer-staged-benign-tool"],
        observe=unavailable_observation,
    )
    assert step.classification is Classification.inconclusive
    assert [obs.template_id for obs in step.observations] == [
        "transfer-benign-payload",
        "transfer-staged-benign-tool",
    ]
