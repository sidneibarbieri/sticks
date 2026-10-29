#!/usr/bin/env python3
"""Admit and execute four bounded discovery procedures in an isolated Linux target."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from concretization.models import ActionTemplate, BindingCatalog, BindingValue, ProcedureProposal
from concretization.verifier import assess_candidate
from evaluation.technique_coverage import indexed_step_count
from executors.discovery_qualification import PROCEDURES, effect_matches

IMAGE = 'alpine@sha256:310c62b5e7ca5b08167e4384c68db0fd2905dd9c7493756d356e893909057601'
CATALOG = ROOT / 'data/concretization/extensions/linux_discovery.json'
INITIAL_FACTS = ['access.target.shell', 'sut.linux.procfs', 'sut.discovery.fixture']


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docker(*arguments: str) -> str:
    return subprocess.run(['docker', *arguments], capture_output=True, text=True,
                          check=True, timeout=60).stdout.strip()


def record_command(container: str, command: tuple[str, ...], path: Path) -> dict:
    result = subprocess.run(['docker', 'exec', container, *command], capture_output=True,
                            text=True, check=False, timeout=20)
    record = {'argv': list(command), 'exit_code': result.returncode,
              'stdout': result.stdout, 'stderr': result.stderr,
              'stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest()}
    path.write_text(json.dumps(record, indent=2) + '\n')
    return record


def admit(template: ActionTemplate, container: str):
    catalog = BindingCatalog(sut_id='linux-discovery-target', source_sha256=digest(CATALOG),
                             initial_facts=INITIAL_FACTS,
                             bindings=[BindingValue(binding_id='target.lab', kind='target_host',
                                                    value=container, source='sut')])
    proposal = ProcedureProposal(technique_id=template.technique_ids[0],
                                 template_id=template.template_id, bindings={'target': 'target.lab'})
    return assess_candidate(proposal, technique_id=template.technique_ids[0],
                            execution_domain='target', templates={template.template_id: template},
                            catalog=catalog, known_facts=set(INITIAL_FACTS))


def measure_reach(qualified: set[str]) -> dict:
    counts = Counter(step['technique_id']
                     for path in (ROOT / 'release/plans/enterprise').glob('*.procedural-plan.json')
                     for step in json.loads(path.read_text())['steps'])
    trusted = {technique for template in json.loads(
        (ROOT / 'data/concretization/action_templates.json').read_text())['templates']
        for technique in template['technique_ids']}
    return {'corpus_steps': sum(counts.values()),
            'baseline_index_reach': indexed_step_count(counts, trusted),
            'extension_index_reach': indexed_step_count(counts, qualified - trusted),
            'union_index_reach': indexed_step_count(counts, trusted | qualified),
            'note': 'Technique-index reach; corpus campaign executions were not performed.'}


def run(output: Path, image: str) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    templates = {item['template_id']: ActionTemplate.model_validate(item)
                 for item in json.loads(CATALOG.read_text())['templates']}
    image_id = docker('image', 'inspect', image, '--format', '{{.Id}}')
    container = 'sticks-discovery-' + uuid.uuid4().hex[:12]
    report = {'schema_version': '1', 'image_id': image_id, 'image_reference': image,
              'execution_locus': 'target', 'access_origin': 'harness_provided_docker_exec',
              'initial_access_demonstrated': False, 'stealth_evaluated': False,
              'observer_independence': 'separate_process_shared_control_plane',
              'initial_facts': INITIAL_FACTS, 'results': [], 'teardown_clean': False}
    created = False
    try:
        docker('run', '-d', '--name', container, '--network', 'none', '--read-only',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--user', '1000:1000',
               '--pids-limit', '32', '--memory', '64m', '--cpus', '0.5',
               '--tmpfs', '/workspace:rw,noexec,nosuid,size=1m,mode=1777', image_id, 'sleep', '300')
        created = True
        docker('exec', container, 'mkdir', '/workspace/discovery')
        docker('exec', container, 'touch', '/workspace/discovery/alpha.txt', '/workspace/discovery/beta.txt')
        for procedure in PROCEDURES:
            assessment = admit(templates[procedure.template_id], container)
            if not assessment.accepted:
                raise ValueError(assessment.model_dump_json())
            command_path = output / f'{procedure.technique_id}.command.json'
            observation_path = output / f'{procedure.technique_id}.observation.json'
            result = record_command(container, procedure.command, command_path)
            observation = record_command(container, procedure.observation_command, observation_path)
            valid = (result['exit_code'] == observation['exit_code'] == 0
                     and effect_matches(procedure.technique_id, result['stdout'], observation['stdout']))
            report['results'].append({'technique_id': procedure.technique_id,
                                      'template_id': procedure.template_id,
                                      'admission': assessment.model_dump(mode='json'),
                                      'effect_observed': valid,
                                      'command_evidence': command_path.name,
                                      'observation_evidence': observation_path.name})
    finally:
        if created:
            docker('rm', '-f', container)
            report['teardown_clean'] = not docker('ps', '-aq', '--filter', f'name=^{container}$')
        qualified = {item['technique_id'] for item in report['results'] if item['effect_observed']}
        report['qualified_techniques'] = sorted(qualified)
        report['index_reach'] = measure_reach(qualified)
        report['evidence_sha256'] = {path.name: digest(path) for path in sorted(output.glob('*.json'))}
        inputs = [CATALOG, Path(__file__).resolve(), ROOT / 'src/executors/discovery_qualification.py',
                  ROOT / 'src/concretization/verifier.py', ROOT / 'data/concretization/action_templates.json']
        inputs += sorted((ROOT / 'release/plans/enterprise').glob('*.procedural-plan.json'))
        report['inputs_sha256'] = {str(path.relative_to(ROOT)): digest(path) for path in inputs}
        (output / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
    if len(report['qualified_techniques']) != len(PROCEDURES) or not report['teardown_clean']:
        raise RuntimeError(f'Qualification incomplete; inspect {output / "qualification.json"}')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory; never overwritten')
    parser.add_argument('--image', default=IMAGE, help='Local immutable image digest')
    args = parser.parse_args()
    if '@sha256:' not in args.image and not args.image.startswith('sha256:'):
        parser.error('--image must use an immutable digest')
    report = run(args.output, args.image)
    print(json.dumps({'qualified': report['qualified_techniques'],
                      'teardown_clean': report['teardown_clean'], 'reach': report['index_reach']}, indent=2))


if __name__ == '__main__':
    main()
