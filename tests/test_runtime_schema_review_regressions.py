"""Independent review counterexamples for impossible runtime evidence states."""

import pytest
from pydantic import ValidationError

from tests.test_runtime_journal import record
from runners.capability_facts import CapabilityFact
from runners.runtime_campaign_report import RuntimeCampaignStep
from runners.runtime_invocation import RuntimeOccurrenceOutcome
from runners.runtime_journal import RuntimeJournalRecord


def test_observed_status_requires_an_actual_observation_outcome():
    with pytest.raises(ValidationError):
        RuntimeCampaignStep(contract=record().contract, status="observed", outcome=None)


def test_successful_executor_alone_cannot_count_as_observed_effect():
    outcome = RuntimeOccurrenceOutcome(
        invocation=record().invocation,
        observations=(),
        observation_references=(),
        authorizing_facts=(),
    )
    with pytest.raises(ValidationError):
        RuntimeCampaignStep(
            contract=record().contract, status="observed", outcome=outcome
        )


def test_simulated_facts_cannot_appear_in_failed_controlled_checkpoint():
    original = record()
    simulated = CapabilityFact(
        name="claimed",
        origin="simulation",
        scope=original.contract.scope,
        producer_occurrence=1,
        observation=None,
    )
    fields = original.model_dump()
    fields["invocation"]["executor_completed"] = False
    fields["simulated_facts"] = (simulated,)
    with pytest.raises(ValidationError):
        RuntimeJournalRecord.model_validate(fields)
