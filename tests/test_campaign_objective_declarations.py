"""The declared campaign objectives are well-formed and observable."""

from pathlib import Path

import pytest

from runners.campaign_objective import load_objective, unobservable_facts
from runners.capability_authority import registered_products

OBJECTIVES_DIR = Path(__file__).resolve().parents[1] / "data" / "campaign_objectives"


def _objective_files() -> list[Path]:
    return sorted(OBJECTIVES_DIR.glob("*.json"))


def test_at_least_one_objective_is_declared() -> None:
    assert _objective_files()


@pytest.mark.parametrize("path", _objective_files(), ids=lambda path: path.stem)
def test_objective_filename_matches_its_campaign(path: Path) -> None:
    objective = load_objective(path)
    assert objective.campaign_id == path.stem


@pytest.mark.parametrize("path", _objective_files(), ids=lambda path: path.stem)
def test_objective_names_only_observable_terminal_facts(path: Path) -> None:
    objective = load_objective(path)
    assert unobservable_facts(objective, registered_products()) == ()
