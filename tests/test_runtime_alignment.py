"""An explicit runtime order must preserve a complete causal realization."""

import json
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from concretization.models import BindingCatalog, ConcretizedPlan
from evaluation.runtime_alignment import align_plan_to_runtime, runtime_techniques
from evaluation.controlled_comparison import AdmittedCampaignPlan, ArmId, NeutralProposalRecord
from evaluation.execution_bridge import build_execution_semantic_bridge

ROOT = Path(__file__).resolve().parents[1]


def cli_environment():
    return {**os.environ, 'PYTHONPATH': os.pathsep.join(filter(None, [
        str(ROOT / 'src'), os.environ.get('PYTHONPATH', '')
    ]))}


def inputs():
    plan = ConcretizedPlan.model_validate_json(
        (ROOT / 'release/plans/C0010.concretized-plan.json').read_text())
    catalog = BindingCatalog.model_validate_json(
        (ROOT / 'release/plans/C0010.binding-catalog.json').read_text())
    runtime = (ROOT / 'data/runtime_contracts/c0010.json').read_bytes()
    return plan, catalog, runtime


def test_alignment_preserves_input_and_certifies_runtime_order():
    plan, catalog, runtime = inputs()
    original = plan.model_dump_json()
    aligned = align_plan_to_runtime(plan, catalog, runtime)
    assert [step.technique_id for step in aligned.steps] == [
        'T1584.001', 'T1608.001', 'T1608.004', 'T1189', 'T1587.001',
        'T1583.001', 'T1608.002', 'T1588.002', 'T1105']
    assert aligned.planning_certificate.valid
    assert len(aligned.planning_certificate.transitions) == 9
    assert aligned.content_sha256 != plan.content_sha256
    assert aligned.execution_semantic_sha256 != plan.execution_semantic_sha256
    assert plan.model_dump_json() == original
    assert {step.technique_id: step.model_dump(exclude={'sequence'}) for step in aligned.steps} == {
        step.technique_id: step.model_dump(exclude={'sequence'}) for step in plan.steps}


def test_alignment_rejects_consumer_before_causal_producer():
    plan, catalog, runtime = inputs()
    document = json.loads(runtime)
    rows = document['occurrences']
    rows[2], rows[3] = rows[3], rows[2]
    for occurrence, row in enumerate(rows, 1):
        row['occurrence'] = occurrence
    with pytest.raises(ValueError, match='causal'):
        align_plan_to_runtime(plan, catalog, json.dumps(document).encode())


def test_alignment_rejects_another_campaign():
    plan, catalog, runtime = inputs()
    document = json.loads(runtime)
    document['campaign_id'] = '0.c0045'
    with pytest.raises(ValueError, match='campaign'):
        align_plan_to_runtime(plan, catalog, json.dumps(document).encode())


def test_runtime_order_accepts_reviewed_shadowray_identity():
    runtime = json.dumps({'campaign_id': '0.shadowray',
        'occurrences': [{'occurrence': 1, 'technique_id': 'T1190'}]}).encode()
    assert runtime_techniques(runtime, 'C0045') == ('T1190',)


def test_runtime_order_rejects_unknown_campaign_identity():
    runtime = json.dumps({'campaign_id': '0.c9999',
        'occurrences': [{'occurrence': 1, 'technique_id': 'T1190'}]}).encode()
    with pytest.raises(ValueError, match='No reviewed runtime identity'):
        runtime_techniques(runtime, 'C9999')


def test_alignment_rejects_duplicated_occurrences():
    plan, catalog, runtime = inputs()
    document = json.loads(runtime)
    document['occurrences'][1]['occurrence'] = 1
    with pytest.raises(ValueError, match='contiguous'):
        align_plan_to_runtime(plan, catalog, json.dumps(document).encode())


def test_alignment_rejects_changed_source_plan():
    plan, catalog, runtime = inputs()
    plan.steps[0].requires = []
    with pytest.raises(ValueError, match='plan hash'):
        align_plan_to_runtime(plan, catalog, runtime)


def test_alignment_rejects_changed_binding_catalog():
    plan, catalog, runtime = inputs()
    catalog.initial_facts.append('undeclared.fact')
    with pytest.raises(ValueError, match='catalog hash'):
        align_plan_to_runtime(plan, catalog, runtime)


def test_alignment_rejects_repeated_techniques_without_occurrence_identity():
    plan, catalog, runtime = inputs()
    document = json.loads(runtime)
    document['occurrences'][1]['technique_id'] = document['occurrences'][0]['technique_id']
    with pytest.raises(ValueError, match='unique'):
        align_plan_to_runtime(plan, catalog, json.dumps(document).encode())


def test_runtime_digest_changes_plan_identity_even_for_same_order():
    plan, catalog, runtime = inputs()
    aligned = align_plan_to_runtime(plan, catalog, runtime)
    other_bytes = json.dumps(json.loads(runtime)).encode()
    changed = align_plan_to_runtime(plan, catalog, other_bytes)
    assert changed.steps == aligned.steps
    assert changed.content_sha256 != aligned.content_sha256
    assert hashlib.sha256(runtime).hexdigest() in aligned.ordering_policy


def test_alignment_cli_refuses_to_replace_existing_output(tmp_path):
    output = tmp_path / 'candidate.json'
    output.write_text('retained evidence')
    result = subprocess.run([
        sys.executable, '-m', 'evaluation.runtime_alignment',
        '--plan', str(ROOT / 'release/plans/C0010.concretized-plan.json'),
        '--catalog', str(ROOT / 'release/plans/C0010.binding-catalog.json'),
        '--runtime', str(ROOT / 'data/runtime_contracts/c0010.json'),
        '--output', str(output),
    ], capture_output=True, text=True, env=cli_environment())
    assert result.returncode != 0
    assert 'FileExistsError' in result.stderr
    assert output.read_text() == 'retained evidence'


def test_alignment_cli_writes_prepared_plan_without_claiming_execution(tmp_path):
    output = tmp_path / 'candidate.json'
    result = subprocess.run([
        sys.executable, '-m', 'evaluation.runtime_alignment',
        '--plan', str(ROOT / 'release/plans/C0010.concretized-plan.json'),
        '--catalog', str(ROOT / 'release/plans/C0010.binding-catalog.json'),
        '--runtime', str(ROOT / 'data/runtime_contracts/c0010.json'),
        '--output', str(output),
    ], capture_output=True, text=True, check=True, env=cli_environment())
    receipt = json.loads(result.stdout)
    assert receipt['status'] == 'prepared_not_executed'
    document = ConcretizedPlan.model_validate_json(output.read_bytes())
    assert document.content_sha256 == receipt['aligned_plan_sha256']
    assert document.planning_certificate.valid


def test_aligned_plan_can_bind_exact_runtime_semantics(tmp_path):
    plan, catalog, runtime = inputs()
    aligned = align_plan_to_runtime(plan, catalog, runtime)
    candidate_path = tmp_path / 'candidate.json'
    candidate_path.write_text(aligned.model_dump_json())
    proposals = []
    for step in aligned.steps:
        proposal = NeutralProposalRecord(
            proposal_id=f'alignment-test-{step.sequence}', experiment_id='alignment-test',
            campaign_id='C0010', step_id=f's{step.sequence}', arm_id=ArmId.sticks_admitted,
            seed=1, technique_id=step.technique_id, execution_domain='linux',
            template_id=step.template_id, bindings=step.bindings,
            proposal_budget_sha256='a' * 64, raw_output_sha256='b' * 64)
        proposal.finalize_hash()
        proposals.append(proposal)
    admitted = AdmittedCampaignPlan(
        experiment_id='alignment-test', campaign_id='C0010', seed=1,
        collection_lock_sha256='c' * 64, proposals=proposals)
    admitted.finalize_hash()
    bridge = build_execution_semantic_bridge(admitted, concretized_plan_path=candidate_path,
        runtime_contract_path=ROOT / 'data/runtime_contracts/c0010.json')
    assert len(bridge.steps) == 9
    assert bridge.runtime_campaign_id == '0.c0010'
    assert bridge.steps[8].technique_id == 'T1105'
