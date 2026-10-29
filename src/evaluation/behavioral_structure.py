"""Measure whether campaign technique sets share structure beyond what their sizes imply.

If campaigns fell into a few behavioral families, a family-level playbook could stand in for
per-step admission. This module tests that on the corpus itself, independent of any catalog.

Each campaign is the set of active techniques it reaches through `uses`. Similarity is the
Jaccard index between two sets. The reference is a null that keeps every campaign's size and
every technique's frequency fixed and randomizes only which campaign uses which technique
(curveball swaps). Structure the null reproduces follows from the marginals alone.

STIX records no order between a campaign's techniques. An ordered-subsequence measure under a
canonical tactic order therefore reduces to the size of the shared set, so we report the
shared set directly instead of an ordering the corpus does not contain.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Sequence
from itertools import combinations

from pydantic import BaseModel, ConfigDict

from evaluation.corpus_characterization import (
    CAMPAIGN,
    USES,
    _is_active,
    technique_identifiers,
)

FAMILY_SIMILARITY = 0.5
NULL_DRAWS = 1000
SWAPS_PER_DRAW = 2000
SEED = 20261007


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SimilaritySummary(StrictModel):
    mean_pairwise_jaccard: float
    mean_nearest_neighbor_jaccard: float
    family_share: float


class NullComparison(StrictModel):
    draws: int
    draws_at_least_observed: int
    null_mean: float
    null_low: float
    null_high: float
    p_at_least_observed: float


class BehavioralStructure(StrictModel):
    question: str
    campaigns: int
    median_techniques: int
    median_shared_techniques: int
    family_similarity: float
    observed: SimilaritySummary
    families: int
    nearest_neighbor_null: NullComparison
    pairwise_null: NullComparison
    note: str


def campaign_technique_sets(bundle: dict) -> list[frozenset[str]]:
    """Active technique set of every active campaign that reaches at least one technique."""
    objects = bundle["objects"]
    techniques = technique_identifiers(objects)
    campaigns = {
        item["id"] for item in objects if item.get("type") == CAMPAIGN and _is_active(item)
    }
    sets: dict[str, set[str]] = {campaign: set() for campaign in campaigns}
    for item in objects:
        if (
            item.get("type") == "relationship"
            and item.get("relationship_type") == USES
            and _is_active(item)
            and item.get("source_ref") in sets
            and item.get("target_ref") in techniques
        ):
            sets[item["source_ref"]].add(techniques[item["target_ref"]])
    return [frozenset(sets[key]) for key in sorted(sets) if sets[key]]


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = len(left | right)
    return len(left & right) / union if union else 0.0


def summarize(sets: Sequence[frozenset[str]]) -> SimilaritySummary:
    if len(sets) < 2:
        raise ValueError("similarity needs at least two campaigns")
    nearest = [0.0] * len(sets)
    pairwise = []
    for left, right in combinations(range(len(sets)), 2):
        value = jaccard(sets[left], sets[right])
        pairwise.append(value)
        nearest[left] = max(nearest[left], value)
        nearest[right] = max(nearest[right], value)
    return SimilaritySummary(
        mean_pairwise_jaccard=statistics.fmean(pairwise),
        mean_nearest_neighbor_jaccard=statistics.fmean(nearest),
        family_share=sum(value >= FAMILY_SIMILARITY for value in nearest) / len(sets),
    )


def families(sets: Sequence[frozenset[str]]) -> int:
    """Connected groups of two or more campaigns linked by similarity at the family threshold."""
    parent = list(range(len(sets)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left, right in combinations(range(len(sets)), 2):
        if jaccard(sets[left], sets[right]) >= FAMILY_SIMILARITY:
            parent[root(left)] = root(right)
    sizes: dict[int, int] = {}
    for index in range(len(sets)):
        sizes[root(index)] = sizes.get(root(index), 0) + 1
    return sum(size >= 2 for size in sizes.values())


def curveball(sets: Sequence[frozenset[str]], swaps: int, rng: random.Random) -> list[frozenset[str]]:
    """Randomize membership while keeping every set size and every item frequency."""
    rows = [set(row) for row in sets]
    for _ in range(swaps):
        left, right = rng.sample(range(len(rows)), 2)
        left_only = list(rows[left] - rows[right])
        right_only = list(rows[right] - rows[left])
        if not left_only or not right_only:
            continue
        pool = sorted(left_only + right_only)
        rng.shuffle(pool)
        shared = rows[left] & rows[right]
        rows[left] = shared | set(pool[: len(left_only)])
        rows[right] = shared | set(pool[len(left_only):])
    return [frozenset(row) for row in rows]


def _compare(observed: float, draws: list[float]) -> NullComparison:
    ordered = sorted(draws)
    return NullComparison(
        draws=len(draws),
        draws_at_least_observed=sum(value >= observed for value in draws),
        null_mean=statistics.fmean(draws),
        null_low=ordered[int(0.025 * len(ordered))],
        null_high=ordered[int(0.975 * len(ordered)) - 1],
        p_at_least_observed=(1 + sum(value >= observed for value in draws)) / (1 + len(draws)),
    )


def measure(
    sets: Sequence[frozenset[str]],
    null_draws: int = NULL_DRAWS,
    swaps: int = SWAPS_PER_DRAW,
    seed: int = SEED,
) -> BehavioralStructure:
    observed = summarize(sets)
    rng = random.Random(seed)
    null = [summarize(curveball(sets, swaps, rng)) for _ in range(null_draws)]
    shared = [len(left & right) for left, right in combinations(sets, 2)]
    return BehavioralStructure(
        question=(
            "Do campaign technique sets fall into behavioral families beyond what campaign "
            "sizes and technique frequencies imply?"
        ),
        campaigns=len(sets),
        median_techniques=int(statistics.median(len(row) for row in sets)),
        median_shared_techniques=int(statistics.median(shared)),
        family_similarity=FAMILY_SIMILARITY,
        observed=observed,
        families=families(sets),
        nearest_neighbor_null=_compare(
            observed.mean_nearest_neighbor_jaccard,
            [draw.mean_nearest_neighbor_jaccard for draw in null],
        ),
        pairwise_null=_compare(
            observed.mean_pairwise_jaccard, [draw.mean_pairwise_jaccard for draw in null]
        ),
        note=(
            "Similarity of technique sets, not of procedures: two campaigns with identical "
            "sets can still differ in every executable detail. STIX records no order, so no "
            "ordered-sequence statistic is reported."
        ),
    )
