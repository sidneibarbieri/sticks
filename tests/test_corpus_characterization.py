"""The corpus characterization reports what the bundle documents, not what runs.

Campaigns and intrusion sets reach different portions of the technique space. The measurement
is a property of the pinned bundle and is independent of the template catalog, so it answers
what the intelligence documents rather than what this artifact can execute.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.corpus_characterization import characterize  # noqa: E402

RECORD = (
    PROJECT_ROOT / "release" / "experiments" / "corpus_characterization" / "corpus.json"
)
BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_the_four_populations_partition_the_technique_space():
    record = _record()
    partition = (
        record["campaign_only"]
        + record["referenced_by_both"]
        + record["intrusion_set_only"]
        + record["referenced_by_neither"]
    )
    assert partition == record["active_techniques"]


def test_each_population_total_agrees_with_its_parts():
    record = _record()
    assert (
        record["campaign_only"] + record["referenced_by_both"]
        == record["campaign_referenced"]
    )
    assert (
        record["intrusion_set_only"] + record["referenced_by_both"]
        == record["intrusion_set_referenced"]
    )


def test_intrusion_sets_reach_more_techniques_than_campaigns():
    """Aggregation across operations reaches wider than any single documented operation."""
    record = _record()
    assert record["intrusion_set_referenced"] > record["campaign_referenced"]


def test_the_record_regenerates_from_the_pinned_bundle():
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    assert characterize(bundle).model_dump(mode="json") == _record()
