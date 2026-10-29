"""Count explicit technique membership, without inferred parent or sibling support."""

from collections.abc import Mapping, Set


def indexed_step_count(step_counts: Mapping[str, int], techniques: Set[str]) -> int:
    """Count each corpus occurrence once when its exact identifier is indexed."""
    return sum(count for technique, count in step_counts.items() if technique in techniques)


def coverage_extension(
    step_counts: Mapping[str, int], trusted: Set[str], drafts: Set[str]
) -> dict[str, int | float]:
    """Separate draft reach from incremental reach where catalogs overlap."""
    total = sum(step_counts.values())
    extended = indexed_step_count(step_counts, trusted | drafts)
    return {
        "total_steps": total,
        "trusted_contract_reach_steps": indexed_step_count(step_counts, trusted),
        "admitted_step_reach": indexed_step_count(step_counts, drafts),
        "incremental_draft_reach_steps": indexed_step_count(step_counts, drafts - trusted),
        "extended_contract_reach_steps": extended,
        "extended_contract_reach_share": round(extended / total, 4) if total else 0.0,
    }
