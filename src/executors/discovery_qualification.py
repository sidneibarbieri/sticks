"""Bounded Linux discovery mechanisms and separate-process observation checks.

The observer shares Docker's control-plane trust boundary. It is not independent
host telemetry, a detection evaluation, or proof of initial compromise.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveryProcedure:
    technique_id: str
    template_id: str
    command: tuple[str, ...]
    observation_command: tuple[str, ...]


PROCEDURES = (
    DiscoveryProcedure('T1082', 'discover-lab-system', ('uname', '-s'),
                       ('cat', '/proc/sys/kernel/ostype')),
    DiscoveryProcedure('T1033', 'discover-lab-user', ('id', '-u'),
                       ('cat', '/proc/1/status')),
    DiscoveryProcedure('T1057', 'discover-lab-processes', ('ps', '-o', 'pid,comm'),
                       ('cat', '/proc/1/comm')),
    DiscoveryProcedure('T1083', 'discover-lab-files',
                       ('find', '/workspace/discovery', '-maxdepth', '1', '-type', 'f'),
                       ('ls', '-1', '/workspace/discovery')),
)


def effect_matches(technique_id: str, output: str, observation: str) -> bool:
    """Reject empty or inconsistent evidence rather than accepting exit status."""
    if not output.strip() or not observation.strip():
        return False
    if technique_id == 'T1082':
        return output.strip() == observation.strip() == 'Linux'
    if technique_id == 'T1033':
        user_rows = [line.split()[1:] for line in observation.splitlines()
                     if line.startswith('Uid:')]
        return (len(user_rows) == 1 and len(user_rows[0]) == 4
                and output.strip().isdigit() and output.strip() == user_rows[0][1])
    if technique_id == 'T1057':
        process_rows = [line.split() for line in output.splitlines()]
        return any(len(row) == 2 and row[0] == '1' and row[1] == observation.strip()
                   for row in process_rows)
    if technique_id == 'T1083':
        discovered = set(output.splitlines())
        observed = {'/workspace/discovery/' + name for name in observation.splitlines()}
        return discovered == observed == {'/workspace/discovery/alpha.txt',
                                          '/workspace/discovery/beta.txt'}
    raise ValueError(f'No observation predicate for technique {technique_id}')
