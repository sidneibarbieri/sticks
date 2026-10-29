"""Catalog feasibility must not depend on the order of binding declarations."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import analyze_controlled_comparison as analysis  # noqa: E402
from concretization.models import (  # noqa: E402
    ActionTemplate,
    BindingCatalog,
    BindingScope,
    BindingValue,
)
from evaluation.comparison_runner import CampaignFixture, StepFixture  # noqa: E402
from evaluation.controlled_comparison import ArmId  # noqa: E402


@pytest.mark.parametrize(
    ("include_lab_binding", "expected_recoverable"),
    [(True, 1), (False, 0)],
)
def test_abstention_profile_checks_lab_binding_after_external_one(
    monkeypatch: pytest.MonkeyPatch,
    include_lab_binding: bool,
    expected_recoverable: int,
) -> None:
    bindings = [
        BindingValue(
            binding_id="external.host",
            kind="host",
            value="outside",
            source="stix",
            scope=BindingScope.external,
        )
    ]
    if include_lab_binding:
        bindings.append(
            BindingValue(
                binding_id="lab.host",
                kind="host",
                value="inside",
                source="sut",
                scope=BindingScope.lab,
            )
        )
    fixture = CampaignFixture(
        campaign_id="TEST",
        steps=[
            StepFixture(
                step_id="s1",
                technique_id="T0001",
                execution_domain="linux",
                objective="bounded fixture",
                tactic="test",
            )
        ],
        templates=[
            ActionTemplate(
                template_id="template",
                technique_ids=["T0001"],
                execution_domain="linux",
                parameter_kinds={"target": "host"},
                produces=["done"],
                evidence_predicates=["file_exists"],
                fidelity_ceiling="adapted",
                description="bounded fixture",
            )
        ],
        catalog=BindingCatalog(
            sut_id="test-sut",
            source_sha256="0" * 64,
            bindings=bindings,
        ),
    )
    monkeypatch.setattr(analysis, "load_campaign_fixture", lambda _: fixture)

    profile = analysis.abstention_profile(
        [{"campaign_id": "TEST", "step_id": "s1", "arm_id": ArmId.sticks_admitted.value, "abstained": True}],
        ["TEST"],
    )

    assert profile["recoverable_proposer_miss"] == expected_recoverable
    assert profile["justified_no_admissible_realization"] == 1 - expected_recoverable
