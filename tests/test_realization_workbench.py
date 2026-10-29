from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.workbench import (  # noqa: E402
    CurationReadinessStatus,
    RealizationWorkbench,
    WorkbenchCurationReadinessRequest,
    WorkbenchEnumerationRequest,
)


def test_static_workbench_assets_are_relative_and_file_urls_fail_closed() -> None:
    """A file preview must not silently lose styling or issue an API request."""

    web_root = PROJECT_ROOT / "web" / "realization-workbench"
    index = (web_root / "index.html").read_text(encoding="utf-8")
    app = (web_root / "app.js").read_text(encoding="utf-8")

    assert 'href="styles.css"' in index
    assert 'src="app.js"' in index
    assert 'href="/styles.css"' not in index
    assert 'src="/app.js"' not in index
    assert 'window.location.protocol === "file:"' in app


@pytest.fixture
def workbench() -> RealizationWorkbench:
    return RealizationWorkbench(PROJECT_ROOT)


def test_inventory_exposes_full_corpus_and_deep_slice(workbench: RealizationWorkbench) -> None:
    inventory = workbench.campaign_inventory()

    assert inventory.campaign_count == 56
    assert inventory.compiled_count == 55
    assert inventory.enumeration_ready_count == 3
    assert inventory.semantic_conformant_count == 3
    ready_ids = {
        campaign.campaign_id for campaign in inventory.campaigns if campaign.enumeration_ready
    }
    assert ready_ids == {"C0010", "C0026", "C0045"}
    assert all(
        campaign.semantic_fact_status == "conformant"
        for campaign in inventory.campaigns
        if campaign.enumeration_ready
    )
    assert all(not (campaign.plan_path or "").startswith("/") for campaign in inventory.campaigns)


def test_enumeration_reuses_frozen_inputs(workbench: RealizationWorkbench) -> None:
    request = WorkbenchEnumerationRequest(
        campaign_id="C0026",
        maximum_realizations=8,
        maximum_search_states=1000,
    )

    first = workbench.enumerate_campaign(request)
    second = workbench.enumerate_campaign(request)

    assert first.interface_scope == "planning_only"
    assert first.result.operational_status == "not_run"
    assert first.result.realization_count == 1
    assert first.generation_queue.operational_status == "not_run"
    assert first.generation_queue.total_procedure_assignment_deficit == 6
    assert first.generation_queue.total_behavior_contract_deficit == 6
    assert first.generation_queue.selected_target_count == 6
    assert first.result.content_sha256 == second.result.content_sha256
    assert first.generation_queue.content_sha256 == second.generation_queue.content_sha256


def test_campaign_without_binding_catalog_is_rejected(workbench: RealizationWorkbench) -> None:
    request = WorkbenchEnumerationRequest(campaign_id="C0001")

    with pytest.raises(ValueError, match="binding catalog is absent"):
        workbench.enumerate_campaign(request)


def test_curation_readiness_audit_marks_absent_inputs_without_claiming_execution(
    workbench: RealizationWorkbench,
) -> None:
    report = workbench.audit_curation_readiness(
        WorkbenchCurationReadinessRequest(
            maximum_realizations=8,
            maximum_search_states=1000,
        )
    )

    rows = {row.campaign_id: row for row in report.rows}
    assert report.interface_scope == "planning_only"
    assert report.operational_status == "not_run"
    assert report.campaign_count == 56
    assert report.frozen_input_ready_count == 3
    assert report.bounded_planning_ready_count == 3
    assert rows["C0001"].curation_status is CurationReadinessStatus.binding_catalog_absent
    assert rows["C0010"].curation_status is CurationReadinessStatus.bounded_planning_ready
    assert rows["C0010"].selected_generation_target_count >= 0
    assert report.validate_hash()


@pytest.mark.parametrize(
    "payload",
    [
        {"campaign_id": "../../C0010"},
        {"campaign_id": "C0010", "maximum_realizations": 0},
        {"campaign_id": "C0010", "maximum_realizations": 257},
        {"campaign_id": "C0010", "maximum_search_states": 100001},
        {"campaign_id": "C0010", "maximum_candidates_per_step": 2049},
        {"campaign_id": "C0010", "desired_procedure_assignments_per_step": 9},
        {"campaign_id": "C0010", "desired_behavior_contracts_per_step": 9},
        {"campaign_id": "C0010", "maximum_generation_targets": 65},
    ],
)
def test_request_rejects_unbounded_or_path_like_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        WorkbenchEnumerationRequest.model_validate(payload)
