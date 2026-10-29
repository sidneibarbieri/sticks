from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from executors.discovery_qualification import effect_matches


@pytest.mark.parametrize('technique,output,observation', [
    ('T1082', 'Linux\n', 'Linux\n'),
    ('T1033', '1000\n', 'Name:\tsleep\nUid:\t1000\t1000\t1000\t1000\n'),
    ('T1057', 'PID COMMAND\n1 sleep\n12 ps\n', 'sleep\n'),
    ('T1083', '/workspace/discovery/beta.txt\n/workspace/discovery/alpha.txt\n', 'alpha.txt\nbeta.txt\n'),
])
def test_effect_requires_matching_observation(technique, output, observation):
    assert effect_matches(technique, output, observation)
    assert not effect_matches(technique, '', observation)
    assert not effect_matches(technique, output, '')
    assert not effect_matches(technique, 'success', observation)
    assert not effect_matches(technique, output, 'inconsistent observation')


def test_process_existence_requires_identity_not_just_any_pid():
    assert not effect_matches('T1057', 'PID COMMAND\n2 sleep\n', 'sleep')
    assert not effect_matches('T1057', 'PID COMMAND\n1 other\n', 'sleep')


def test_user_check_uses_effective_not_real_uid():
    assert not effect_matches('T1033', '1000', 'Uid:\t1000\t0\t0\t0')


def test_preserved_discovery_effects_replay_without_docker():
    spec = importlib.util.spec_from_file_location('discovery_verify', ROOT / 'scripts/verify_linux_discovery.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.verify(ROOT / 'release/experiments/linux_discovery/run-20260919-final') == [
        'T1033', 'T1057', 'T1082', 'T1083']


@pytest.mark.parametrize('mutation', ['access_origin', 'input_hash', 'stdout_hash'])
def test_replay_rejects_changed_scope_or_evidence(tmp_path, mutation):
    spec = importlib.util.spec_from_file_location('discovery_verify', ROOT / 'scripts/verify_linux_discovery.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bundle = tmp_path / 'bundle'
    shutil.copytree(ROOT / 'release/experiments/linux_discovery/run-20260919-final', bundle)
    report_path = bundle / 'qualification.json'
    report = json.loads(report_path.read_text())
    if mutation == 'access_origin':
        report['access_origin'] = 'attacker_demonstrated_initial_access'
    elif mutation == 'input_hash':
        first_input = next(iter(report['inputs_sha256']))
        report['inputs_sha256'][first_input] = '0' * 64
    else:
        name = report['results'][0]['command_evidence']
        evidence_path = bundle / name
        record = json.loads(evidence_path.read_text())
        record['stdout_sha256'] = '0' * 64
        evidence_path.write_text(json.dumps(record))
        report['evidence_sha256'][name] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='interpretation|Input hash mismatch|Stdout hash mismatch'):
        module.verify(bundle)


def test_admission_rejects_missing_target_session():
    import json
    from concretization.models import ActionTemplate, BindingCatalog, BindingValue, ProcedureProposal
    from concretization.verifier import assess_candidate
    template = ActionTemplate.model_validate(json.loads((ROOT / 'data/concretization/extensions/linux_discovery.json').read_text())['templates'][0])
    binding_catalog = BindingCatalog(sut_id='lab', source_sha256='fixture', bindings=[
        BindingValue(binding_id='target.lab', kind='target_host', value='test-target', source='sut')])
    assessment = assess_candidate(
        ProcedureProposal(technique_id='T1082', template_id=template.template_id,
                          bindings={'target': 'target.lab'}),
        technique_id='T1082', execution_domain='target', templates={template.template_id: template},
        catalog=binding_catalog, known_facts={'sut.linux.procfs', 'sut.discovery.fixture'})
    assert not assessment.accepted
    assert any(issue.code == 'UNSATISFIED_PRECONDITIONS' for issue in assessment.issues)
