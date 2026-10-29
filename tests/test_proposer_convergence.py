"""The committed plan does not depend on which proposer supplied it.

The frozen record holds one observation per proposer: the finite-domain solver with no
proposal, a local model sampled twice at temperature 0.7, and a model from a different
family. Sampling makes the proposals differ between runs; the committed plan does not,
because the verifier decides admission over the same finite catalog.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from concretization.pipeline import concretize_plan  # noqa: E402
from concretization.proposer_convergence import model_observation  # noqa: E402
from concretization.provider import LLMCallRecord  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402

CONVERGENCE_DIR = (
    Path(__file__).resolve().parent.parent / "release" / "experiments" / "proposer_convergence"
)
CAMPAIGNS = ("C0010", "C0026", "C0045")
PLANS_DIR = Path(__file__).resolve().parent.parent / "release" / "plans"
TEMPLATES_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "concretization" / "action_templates.json"
)


def _record(campaign_id: str = "C0045") -> dict:
    path = CONVERGENCE_DIR / f"{campaign_id}.convergence.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_proposer_commits_the_same_execution_semantics():
    record = _record()
    hashes = {item["execution_semantic_sha256"] for item in record["observations"]}
    assert len(hashes) == 1, f"proposers disagreed: {sorted(hashes)}"
    assert record["converged"] is True


def test_the_comparison_covers_a_solver_and_more_than_one_model_family():
    proposers = {item["proposer"] for item in _record()["observations"]}
    assert "finite_domain_solver" in proposers
    model_families = {name.split(":")[0] for name in proposers if name != "finite_domain_solver"}
    assert len(model_families) >= 2, f"only one model family present: {model_families}"


def test_sampled_runs_are_recorded_with_their_temperature():
    sampled = [
        item for item in _record()["observations"] if item["proposer"] != "finite_domain_solver"
    ]
    assert sampled, "no model proposer recorded"
    for item in sampled:
        # Temperature is reported so a reader can see the proposals were not made deterministic.
        assert item["temperature"] and item["temperature"] > 0


def test_the_comparison_holds_its_conditions_constant():
    """Only the model varies, so convergence cannot be an artifact of unequal settings."""
    conditions = _record()["controlled_conditions"]
    for field in ("system prompt", "action catalog", "temperature", "verifier version"):
        assert field in conditions["held_constant"]
    assert conditions["varied_across_runs"][0] == "model"


def test_every_run_shares_the_recorded_temperature():
    record = _record()
    temperature = record["controlled_conditions"]["temperature"]
    sampled = [
        item for item in record["observations"] if item["proposer"] != "finite_domain_solver"
    ]
    assert {item["temperature"] for item in sampled} == {temperature}


def test_a_rejected_proposal_is_not_retried_into_acceptance():
    # Single-shot admission: the recorded policy must not allow retrying until something passes.
    assert _record()["controlled_conditions"]["retry_policy"].startswith("none")


def test_every_evaluated_campaign_converges():
    """Each campaign commits one execution semantics regardless of the proposer."""
    for campaign_id in CAMPAIGNS:
        record = _record(campaign_id)
        hashes = {item["execution_semantic_sha256"] for item in record["observations"]}
        assert len(hashes) == 1, f"{campaign_id} disagreed: {sorted(hashes)}"
        assert record["converged"] is True


def test_model_proposers_reach_what_the_solver_commits_alone():
    """A model proposal commits what the solver commits with no proposal at all."""
    templates = [
        ActionTemplate.model_validate(item)
        for item in json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    ]
    for campaign_id in CAMPAIGNS:
        plan = ProceduralPlan.model_validate_json(
            (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
        )
        catalog = BindingCatalog.model_validate_json(
            (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
        )
        solver_only = concretize_plan(plan, catalog, templates, llm_proposals=[])
        for item in _record(campaign_id)["observations"]:
            assert item["execution_semantic_sha256"] == solver_only.execution_semantic_sha256


def test_recorded_model_calls_replay_to_the_reported_execution_semantics():
    templates = [
        ActionTemplate.model_validate(item)
        for item in json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    ]
    for campaign_id in CAMPAIGNS:
        plan = ProceduralPlan.model_validate_json(
            (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
        )
        catalog = BindingCatalog.model_validate_json(
            (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
        )
        for item in _record(campaign_id)["observations"]:
            if item["proposer"] == "finite_domain_solver":
                continue
            call_path = CONVERGENCE_DIR / item["call_record_path"]
            assert hashlib.sha256(call_path.read_bytes()).hexdigest() == item["call_record_sha256"]
            call = LLMCallRecord.model_validate_json(call_path.read_text(encoding="utf-8"))
            replayed = model_observation(
                plan,
                catalog,
                templates,
                call.proposals,
                proposer=item["proposer"],
                temperature=item["temperature"],
                sample=item["sample"],
                malformed_proposals=call.malformed_proposals,
            )
            assert replayed.execution_semantic_sha256 == item["execution_semantic_sha256"]
            assert replayed.committed_from_proposer == item["committed_from_proposer"]
