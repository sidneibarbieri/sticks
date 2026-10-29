from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest  # noqa: E402

from concretization.models import ActionTemplate  # noqa: E402
from concretization.template_admission import build_admission_vocabulary  # noqa: E402
from concretization.template_proposer import (  # noqa: E402
    TemplateProposalContext,
    build_user_prompt,
    propose_template,
    trusted_behavior_contract,
)

TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"


def _catalog() -> list[ActionTemplate]:
    payload = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    return [ActionTemplate.model_validate(item) for item in payload["templates"]]


@pytest.fixture(scope="module")
def vocabulary():
    return build_admission_vocabulary(_catalog())


_ADMISSIBLE = json.dumps(
    {
        "template_id": "open-remote-management-channel",
        "technique_ids": ["T1021.006"],
        "execution_domain": "target",
        "parameter_kinds": {"actor": "actor_host"},
        "requires": ["actor.ready"],
        "produces": ["access.target.remote_session"],
        "evidence_predicates": ["service_request_logged"],
        "fidelity_ceiling": "adapted",
        "description": "Open a bounded remote-management session against the lab target.",
    }
)

_REJECTED = json.dumps(
    {
        "template_id": "invented-cloud-effect",
        "technique_ids": ["T1021.006"],
        "execution_domain": "target",
        "parameter_kinds": {},
        "requires": ["actor.ready"],
        "produces": ["quantum:entangled"],
        "evidence_predicates": ["screenshot_uploaded_to_cloud"],
        "fidelity_ceiling": "real",
        "description": "Uses vocabulary the framework does not implement.",
    }
)

_WRONG_TECHNIQUE = json.dumps(
    {
        **json.loads(_ADMISSIBLE),
        "technique_ids": ["T9999"],
    }
)


def _scripted(responses):
    calls = {"n": 0}

    def complete(system_prompt: str, user_prompt: str) -> str:
        index = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return responses[index]

    return complete, calls


def _context() -> TemplateProposalContext:
    admissible = ActionTemplate.model_validate_json(_ADMISSIBLE)
    context = TemplateProposalContext(
        campaign_id="CTEST",
        source_step_index=0,
        source_plan_sha256="a" * 64,
        binding_catalog_sha256="b" * 64,
        execution_domain="target",
        admissible_required_facts=["actor.ready"],
        admissible_produced_facts=["access.target.remote_session"],
        available_binding_kinds=["actor_host"],
        existing_template_ids=["existing-template"],
        admissible_behavior_contracts=[trusted_behavior_contract(admissible)],
    )
    context.finalize_hash()
    return context


def test_admissible_proposal_is_accepted_on_first_attempt(vocabulary):
    complete, calls = _scripted([_ADMISSIBLE])
    outcome = propose_template(
        "T1021.006", "Remote Services: WMI", vocabulary, _catalog()[:3], complete
    )
    assert outcome.admitted
    assert outcome.attempts == 1
    assert calls["n"] == 1
    assert outcome.template is not None


def test_rejection_is_retried_then_accepted(vocabulary):
    complete, calls = _scripted([_REJECTED, _ADMISSIBLE])
    outcome = propose_template(
        "T1021.006", "Remote Services: WMI", vocabulary, _catalog()[:3], complete
    )
    assert outcome.admitted
    assert outcome.attempts == 2
    assert calls["n"] == 2


def test_persistent_rejection_is_reported_not_admitted(vocabulary):
    complete, _ = _scripted([_REJECTED])
    outcome = propose_template(
        "T1021.006", "Remote Services: WMI", vocabulary, _catalog()[:3], complete, max_attempts=2
    )
    assert not outcome.admitted
    assert outcome.attempts == 2
    assert outcome.admission is not None
    assert outcome.admission.issues


def test_unparseable_response_is_recorded(vocabulary):
    complete, _ = _scripted(["I cannot help with that."])
    outcome = propose_template(
        "T1021.006", "Remote Services: WMI", vocabulary, _catalog()[:3], complete, max_attempts=2
    )
    assert not outcome.admitted
    assert outcome.parse_errors


def test_prior_issues_are_fed_back_into_the_prompt(vocabulary):
    seen: list[str] = []

    def complete(system_prompt: str, user_prompt: str) -> str:
        seen.append(user_prompt)
        return _REJECTED if len(seen) == 1 else _ADMISSIBLE

    outcome = propose_template(
        "T1021.006", "Remote Services: WMI", vocabulary, _catalog()[:3], complete
    )
    assert outcome.admitted
    assert "previous_rejection" in seen[1]
    assert "previous_rejection" not in seen[0]


def test_template_for_another_technique_is_rejected_and_retried(vocabulary):
    complete, calls = _scripted([_WRONG_TECHNIQUE, _ADMISSIBLE])

    outcome = propose_template(
        "T1021.006",
        "Remote Services: WMI",
        vocabulary,
        _catalog()[:3],
        complete,
    )

    assert outcome.admitted
    assert outcome.attempts == 2
    assert calls["n"] == 2


def test_build_user_prompt_lists_the_enforced_vocabulary(vocabulary):
    prompt = build_user_prompt("T1021.006", "Remote Services: WMI", vocabulary, _catalog()[:2])
    assert "allowed_evidence_predicates" in prompt
    assert "allowed_fidelity_ceilings" in prompt
    assert "allowed_parameter_kinds" in prompt


def test_context_is_hash_bound_and_included_in_prompt(vocabulary):
    context = _context()

    prompt = build_user_prompt(
        "T1021.006",
        "Remote Services: WMI",
        vocabulary,
        _catalog()[:2],
        context=context,
    )

    assert context.content_sha256 in prompt
    assert "admissible_required_facts" in prompt
    assert "available_binding_kinds" in prompt


def test_context_rejection_is_retried(vocabulary):
    outside_context = json.dumps(
        {
            **json.loads(_ADMISSIBLE),
            "produces": ["access.target.unrequested"],
        }
    )
    complete, calls = _scripted([outside_context, _ADMISSIBLE])

    outcome = propose_template(
        "T1021.006",
        "Remote Services: WMI",
        vocabulary,
        _catalog()[:3],
        complete,
        context=_context(),
    )

    assert outcome.admitted
    assert outcome.attempts == 2
    assert calls["n"] == 2


def test_context_rejects_a_new_behavior_contract_even_with_known_vocabulary(vocabulary):
    recombined_contract = json.dumps(
        {
            **json.loads(_ADMISSIBLE),
            "produces": ["access.target.remote_session", "actor.ready"],
        }
    )
    complete, _ = _scripted([recombined_contract])

    outcome = propose_template(
        "T1021.006",
        "Remote Services: WMI",
        vocabulary,
        _catalog()[:3],
        complete,
        max_attempts=1,
        context=_context(),
    )

    assert not outcome.admitted
    assert outcome.admission is not None
    assert any(
        issue.code == "untrusted_behavior_contract" for issue in outcome.admission.issues
    )


def test_tampered_context_is_rejected_before_provider_call(vocabulary):
    context = _context()
    context.execution_domain = "attacker"
    complete, calls = _scripted([_ADMISSIBLE])

    with pytest.raises(ValueError, match="context hash mismatch"):
        propose_template(
            "T1021.006",
            "Remote Services: WMI",
            vocabulary,
            _catalog()[:3],
            complete,
            context=context,
        )

    assert calls["n"] == 0
