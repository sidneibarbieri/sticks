#!/usr/bin/env python3
"""Recompute bounded discovery outcomes from preserved command observations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from executors.discovery_qualification import PROCEDURES, effect_matches


def read_evidence(directory: Path, name: str, expected_hash: str) -> dict:
    if Path(name).name != name:
        raise ValueError('Evidence paths must name files in the bundle directory')
    path = directory / name
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError(f'Evidence hash mismatch: {name}')
    record = json.loads(content)
    if hashlib.sha256(record['stdout'].encode()).hexdigest() != record['stdout_sha256']:
        raise ValueError(f'Stdout hash mismatch: {name}')
    return record


def verify(directory: Path) -> list[str]:
    report = json.loads((directory / 'qualification.json').read_text())
    procedures = {procedure.technique_id: procedure for procedure in PROCEDURES}
    rows = report['results']
    if len(rows) != len(procedures) or {row['technique_id'] for row in rows} != set(procedures):
        raise ValueError('Expected exactly one result per discovery technique')
    if (report['initial_access_demonstrated'] is not False or report['stealth_evaluated'] is not False
            or report['observer_independence'] != 'separate_process_shared_control_plane'
            or report['execution_locus'] != 'target'
            or report['access_origin'] != 'harness_provided_docker_exec'):
        raise ValueError('Unsupported interpretation of the discovery evidence')
    for relative_path, expected_hash in report['inputs_sha256'].items():
        source = (ROOT / relative_path).resolve()
        if not source.is_relative_to(ROOT):
            raise ValueError('Input path escapes the artifact')
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f'Input hash mismatch: {relative_path}')
    verified = []
    for row in rows:
        procedure = procedures[row['technique_id']]
        action = read_evidence(directory, row['command_evidence'], report['evidence_sha256'][row['command_evidence']])
        observation = read_evidence(directory, row['observation_evidence'], report['evidence_sha256'][row['observation_evidence']])
        if action['argv'] != list(procedure.command) or observation['argv'] != list(procedure.observation_command):
            raise ValueError('Evidence refers to a different mechanism or observer')
        if not (action['exit_code'] == observation['exit_code'] == 0
                and effect_matches(procedure.technique_id, action['stdout'], observation['stdout'])):
            raise ValueError(f'Effect not supported: {procedure.technique_id}')
        if row['effect_observed'] is not True or row['admission']['accepted'] is not True:
            raise ValueError('Outcome record disagrees with qualification')
        verified.append(procedure.technique_id)
    if sorted(verified) != report['qualified_techniques'] or report['teardown_clean'] is not True:
        raise ValueError('Qualification or teardown incomplete')
    return sorted(verified)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    print('Verified discovery effects:', ', '.join(verify(args.bundle)))


if __name__ == '__main__':
    main()
