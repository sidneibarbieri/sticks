#!/usr/bin/env python3
"""Measure how the candidate domain grows, and where complete enumeration stops being free.

The admission model rests on the candidate set being finite and completely enumerable. That
is a property of the declared inputs, not an aspiration: the set is the union, over templates
matching the technique, of the cross product of the typed binding domains each template
consumes. This step states that count in closed form, checks the enumerator produces exactly
it, and times enumeration and admission as a laboratory grows.

The point is not that enumeration is cheap. It is that the size is known before enumerating,
so a laboratory too large to enumerate completely is refused rather than silently truncated.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from concretization.models import (  # noqa: E402
    ActionTemplate,
    BindingCatalog,
    BindingValue,
)
from concretization.solver import enumerate_candidates  # noqa: E402
from contracts.procedural_ir import ProcedureStep  # noqa: E402

OUTPUT = PROJECT_ROOT / "release" / "experiments" / "enumeration_scaling" / "corpus.json"
# Host timings are runtime diagnostics, separate from preserved evidence.
TIMING = PROJECT_ROOT / "results" / "enumeration_scaling_timing.json"

TECHNIQUE_ID = "T9999"
BINDINGS_PER_KIND = (1, 2, 4, 8, 16)
PARAMETERS_PER_TEMPLATE = (1, 2, 3)
TEMPLATES_PER_TECHNIQUE = (1, 4, 16)
ENUMERATION_CEILING = 100_000


@dataclass(frozen=True)
class GridPoint:
    """One declared laboratory shape and what enumerating it costs."""

    templates: int
    parameters: int
    bindings_per_kind: int
    predicted_candidates: int
    enumerated_candidates: int
    enumeration_seconds: float
    refused_by_default_ceiling: bool


def build_step() -> ProcedureStep:
    return ProcedureStep(
        technique_id=TECHNIQUE_ID,
        technique_stix_id="attack-pattern--synthetic",
        name="Synthetic scaling probe",
        execution_domain="target",
        relationship_ids=["relationship--synthetic"],
    )


def build_templates(count: int, parameters: int) -> list[ActionTemplate]:
    return [
        ActionTemplate(
            template_id=f"probe-{index:03d}",
            technique_ids=[TECHNIQUE_ID],
            execution_domain="target",
            parameter_kinds={f"param{position}": f"kind{position}" for position in range(parameters)},
            requires=[],
            produces=["probe.effect"],
            evidence_predicates=["artifact_hash_recorded"],
            fidelity_ceiling="inspired",
            description="Synthetic template used only to size the candidate domain.",
        )
        for index in range(count)
    ]


def build_catalog(parameters: int, bindings_per_kind: int) -> BindingCatalog:
    bindings = [
        BindingValue(
            binding_id=f"kind{position}-{index:03d}",
            kind=f"kind{position}",
            value=f"value-{position}-{index}",
            source="system_introduced",
        )
        for position in range(parameters)
        for index in range(bindings_per_kind)
    ]
    return BindingCatalog(
        sut_id="synthetic-scaling-lab",
        source_sha256="0" * 64,
        bindings=bindings,
    )


def predicted_candidate_count(templates: int, parameters: int, bindings_per_kind: int) -> int:
    """Closed form: one cross product of typed domains per matching template."""
    return templates * math.prod([bindings_per_kind] * parameters)


def measure(templates: int, parameters: int, bindings_per_kind: int) -> GridPoint:
    step = build_step()
    catalog = build_catalog(parameters, bindings_per_kind)
    template_objects = build_templates(templates, parameters)
    predicted = predicted_candidate_count(templates, parameters, bindings_per_kind)

    started = time.perf_counter()
    candidates = enumerate_candidates(
        step, template_objects, catalog, maximum_candidates=ENUMERATION_CEILING
    )
    elapsed = time.perf_counter() - started

    return GridPoint(
        templates=templates,
        parameters=parameters,
        bindings_per_kind=bindings_per_kind,
        predicted_candidates=predicted,
        enumerated_candidates=len(candidates),
        enumeration_seconds=round(elapsed, 6),
        refused_by_default_ceiling=predicted > 512,
    )


def refusal_probe() -> dict[str, object]:
    """A laboratory too large to enumerate must be refused, not silently truncated."""
    templates, parameters, bindings_per_kind = 16, 3, 32
    predicted = predicted_candidate_count(templates, parameters, bindings_per_kind)
    step = build_step()
    catalog = build_catalog(parameters, bindings_per_kind)
    template_objects = build_templates(templates, parameters)

    refused = False
    message = ""
    try:
        enumerate_candidates(
            step, template_objects, catalog, maximum_candidates=ENUMERATION_CEILING
        )
    except ValueError as refusal:
        refused = True
        message = str(refusal)

    return {
        "templates": templates,
        "parameters": parameters,
        "bindings_per_kind": bindings_per_kind,
        "predicted_candidates": predicted,
        "ceiling": ENUMERATION_CEILING,
        "refused": refused,
        "refusal_message": message,
    }


def main(*, write_timing: bool = True) -> int:
    points = [
        measure(templates, parameters, bindings)
        for templates in TEMPLATES_PER_TECHNIQUE
        for parameters in PARAMETERS_PER_TEMPLATE
        for bindings in BINDINGS_PER_KIND
    ]

    mismatched = [
        point for point in points if point.predicted_candidates != point.enumerated_candidates
    ]
    if mismatched:
        raise SystemExit(
            f"[enumeration-scaling] closed form disagrees with the enumerator: {mismatched}"
        )

    largest = max(points, key=lambda point: point.enumerated_candidates)
    refusal = refusal_probe()
    if not refusal["refused"]:
        raise SystemExit(
            "[enumeration-scaling] a domain above the ceiling was enumerated instead of refused"
        )
    payload = {
        "question": (
            "How does the complete candidate set grow with the declared catalog and laboratory, "
            "and is its size known before enumeration?"
        ),
        "method": (
            "For each grid point a synthetic catalog and laboratory are declared, the closed-form "
            "candidate count is computed, the enumerator is run, and the two are compared. Any "
            "disagreement fails the step, so a truncated set cannot be reported as complete."
        ),
        "default_ceiling": 512,
        "probe_ceiling": ENUMERATION_CEILING,
        "grid_points": len(points),
        "largest_candidate_set": largest.enumerated_candidates,
        "points_refused_by_default_ceiling": sum(
            1 for point in points if point.refused_by_default_ceiling
        ),
        "closed_form_agrees_everywhere": True,
        "refusal_probe": refusal,
        "points": [
            {
                key: value
                for key, value in point.__dict__.items()
                if key != "enumeration_seconds"
            }
            for point in points
        ],
        "note": (
            "Growth is polynomial in the bindings declared per consumed kind, with the exponent "
            "set by how many typed parameters a template consumes. A laboratory host that no "
            "template consumes adds nothing to the candidate set."
        ),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if write_timing:
        TIMING.parent.mkdir(parents=True, exist_ok=True)
        TIMING.write_text(
            json.dumps(
                {
                    "note": (
                        "Observed on the measuring host. Not part of any registered claim, because "
                        "a wall-clock reading is not reproducible across machines."
                    ),
                    "largest_candidate_set": largest.enumerated_candidates,
                    "largest_enumeration_seconds": largest.enumeration_seconds,
                    "seconds_by_point": {
                        f"{point.templates}x{point.parameters}x{point.bindings_per_kind}":
                            point.enumeration_seconds
                        for point in points
                    },
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
    print(f"[enumeration-scaling] wrote {OUTPUT.relative_to(PROJECT_ROOT)}")
    print(
        f"[enumeration-scaling] {len(points)} grid points, largest complete set "
        f"{largest.enumerated_candidates} in {largest.enumeration_seconds:.4f}s"
    )
    print(
        f"[enumeration-scaling] a {refusal['predicted_candidates']}-candidate domain is refused "
        "rather than truncated"
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-timing-output", action="store_true")
    arguments = parser.parse_args()
    raise SystemExit(main(write_timing=not arguments.no_timing_output))
