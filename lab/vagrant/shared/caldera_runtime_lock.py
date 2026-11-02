"""Verify the installed CALDERA Python runtime against its hashed lock."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import shlex
import sys
from typing import Protocol

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


@dataclass(frozen=True, slots=True)
class LockedDistribution:
    name: str
    version: str
    hashes: tuple[str, ...]


class InstalledDistribution(Protocol):
    version: str
    requires: Sequence[str] | None


def requirement_rows(text: str) -> tuple[str, ...]:
    rows, pending = [], []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        pending.append(line.removesuffix('\\').strip())
        if not line.endswith('\\'):
            rows.append(' '.join(pending))
            pending = []
    if pending:
        raise ValueError('Unterminated runtime lock requirement')
    return tuple(rows)


def parse_lock(text: str) -> tuple[LockedDistribution, ...]:
    locked = {}
    for row in requirement_rows(text):
        tokens = shlex.split(row)
        requirement = Requirement(tokens[0])
        specifiers = tuple(requirement.specifier)
        if (len(specifiers) != 1 or specifiers[0].operator != '=='
                or '*' in specifiers[0].version or requirement.url
                or requirement.marker or requirement.extras):
            raise ValueError('Runtime lock requires unconditional exact package versions')
        if any(not token.startswith('--hash=sha256:') for token in tokens[1:]):
            raise ValueError('Unsupported runtime lock option')
        hashes = tuple(token.removeprefix('--hash=sha256:') for token in tokens[1:])
        if not hashes or any(not re.fullmatch(r'[0-9a-f]{64}', value) for value in hashes):
            raise ValueError('Runtime lock requires SHA-256 hashes for every package')
        name = canonicalize_name(requirement.name)
        if name in locked:
            raise ValueError('Runtime lock contains a duplicate package')
        locked[name] = LockedDistribution(name, specifiers[0].version, hashes)
    if not locked:
        raise ValueError('Runtime lock is empty')
    return tuple(locked[name] for name in sorted(locked))


def active_requirements(rows: Sequence[str], environment: Mapping[str, str]) -> Iterator[Requirement]:
    for row in rows:
        requirement = Requirement(row)
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        if requirement.url or requirement.extras:
            raise ValueError('Runtime dependency requires an explicitly supported lock format')
        yield requirement


def verify_runtime(
    locked: Sequence[LockedDistribution], root_rows: Sequence[str], *,
    distribution: Callable[[str], InstalledDistribution] = metadata.distribution,
    environment: Mapping[str, str] | None = None,
) -> tuple[LockedDistribution, ...]:
    environment = dict(default_environment() if environment is None else environment, extra='')
    packages = {package.name: package for package in locked}
    pending = list(active_requirements(root_rows, environment))
    visited = set()
    while pending:
        requirement = pending.pop()
        name = canonicalize_name(requirement.name)
        if name not in packages:
            raise ValueError(f'Runtime dependency is absent from the lock: {name}')
        package = packages[name]
        if not requirement.specifier.contains(package.version, prereleases=True):
            raise ValueError(f'Locked version violates a runtime requirement: {name}')
        if name in visited:
            continue
        installed = distribution(name)
        if Version(installed.version) != Version(package.version):
            raise ValueError(f'Installed runtime version differs from the lock: {name}')
        visited.add(name)
        pending.extend(active_requirements(installed.requires or (), environment))
    if visited != set(packages):
        raise ValueError('Runtime lock contains packages outside the dependency closure')
    return tuple(packages[name] for name in sorted(visited))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--roots', type=Path, required=True)
    arguments = parser.parse_args()
    if (sys.version_info[:2] != (3, 10) or platform.system() != 'Linux'
            or platform.machine() not in {'aarch64', 'x86_64'}):
        raise RuntimeError('This runtime lock targets Linux ARM64/x86_64 with Python 3.10')
    lock_bytes, root_bytes = arguments.lock.read_bytes(), arguments.roots.read_bytes()
    packages = verify_runtime(parse_lock(lock_bytes.decode()), requirement_rows(root_bytes.decode()))
    print(json.dumps({
        'schema': 'caldera-python-runtime-lock/v1',
        'lock_sha256': hashlib.sha256(lock_bytes).hexdigest(),
        'roots_sha256': hashlib.sha256(root_bytes).hexdigest(),
        'python_version': platform.python_version(), 'machine': platform.machine(),
        'packages': [asdict(package) for package in packages],
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
