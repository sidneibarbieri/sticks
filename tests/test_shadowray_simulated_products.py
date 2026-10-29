"""ShadowRay simulated steps retain their declared evidence origin."""

import json
from pathlib import Path

import pytest

from executors.executor_registry import registry
from executors.registry_initializer import initialize_registry


CAMPAIGN_PATH = Path(__file__).resolve().parents[1] / "campaigns/0.shadowray.json"
SIMULATED_TECHNIQUES = ("T1027.013", "T1003.008", "T1546.004", "T1068", "T1496.001")

initialize_registry()


@pytest.mark.parametrize("technique_id", SIMULATED_TECHNIQUES)
def test_manifest_and_selected_executor_do_not_claim_operational_products(technique_id):
    campaign = json.loads(CAMPAIGN_PATH.read_text(encoding="utf-8"))
    step = next(
        step for step in campaign["techniques"] if step["technique_id"] == technique_id
    )
    metadata = registry.get_metadata(technique_id, "0.shadowray")

    assert metadata is not None
    assert step["expected_mode"] == metadata.execution_mode.value == "naive_simulated"
    assert step["produces"] == metadata.produces
    assert all(product.startswith("simulation:") for product in metadata.produces)
