"""Runtime locks must bind exact versions and the active dependency closure."""

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / 'lab/vagrant/shared'
specification = importlib.util.spec_from_file_location('caldera_runtime_lock', SHARED / 'caldera_runtime_lock.py')
runtime = importlib.util.module_from_spec(specification)
sys.modules[specification.name] = runtime
specification.loader.exec_module(runtime)
HASH = 'a' * 64


@dataclass(frozen=True)
class Distribution:
    version: str
    requires: tuple[str, ...] = ()


def lock(*rows):
    return runtime.parse_lock('\n'.join(f'{row} --hash=sha256:{HASH}' for row in rows))


def test_accepts_complete_runtime_closure():
    installed = {'root': Distribution('1.0', ('child>=2',)), 'child': Distribution('2.0')}
    verified = runtime.verify_runtime(lock('root==1.0', 'child==2.0'), ('root>=1',),
                                      distribution=installed.__getitem__)
    assert tuple(package.name for package in verified) == ('child', 'root')


@pytest.mark.parametrize('text', (
    'root>=1 --hash=sha256:' + HASH,
    'root==1.* --hash=sha256:' + HASH,
    'root==1.0',
    'root==1.0 --hash=sha256:bad',
    'root==1.0 ' + HASH,
    'root==1.0; python_version>="3.10" --hash=sha256:' + HASH,
    'root==1.0 --hash=sha256:' + HASH + '\nroot==1.0 --hash=sha256:' + HASH,
    'root==1.0 \\',
))
def test_rejects_unpinned_unhashed_or_ambiguous_lock(text):
    with pytest.raises(ValueError):
        runtime.parse_lock(text)


def test_rejects_installed_version_drift():
    with pytest.raises(ValueError, match='Installed runtime version'):
        runtime.verify_runtime(lock('root==1.0'), ('root>=1',),
                               distribution=lambda name: Distribution('1.1'))


def test_rejects_missing_transitive_lock_entry():
    with pytest.raises(ValueError, match='absent from the lock: child'):
        runtime.verify_runtime(lock('root==1.0'), ('root>=1',),
                               distribution=lambda name: Distribution('1.0', ('child>=2',)))


def test_rejects_transitive_version_incompatible_with_parent():
    installed = {'root': Distribution('1.0', ('child>=3',)), 'child': Distribution('2.0')}
    with pytest.raises(ValueError, match='violates a runtime requirement: child'):
        runtime.verify_runtime(lock('root==1.0', 'child==2.0'), ('root>=1',),
                               distribution=installed.__getitem__)


def test_ignores_inactive_optional_dependency_and_respects_python_marker():
    installed = {'root': Distribution('1.0', ('optional; extra=="docs"',
                                            'child; python_version<"3.11"')),
                 'child': Distribution('2.0')}
    runtime.verify_runtime(lock('root==1.0', 'child==2.0'), ('root>=1',),
                           distribution=installed.__getitem__,
                           environment={'python_version': '3.10', 'extra': ''})


def test_rejects_unreachable_package():
    with pytest.raises(ValueError, match='outside the dependency closure'):
        runtime.verify_runtime(lock('root==1.0', 'unused==2.0'), ('root>=1',),
                               distribution=lambda name: Distribution('1.0'))


def test_real_lock_has_hashes_and_satisfies_all_declared_roots():
    packages = {package.name: package for package in runtime.parse_lock(
        (SHARED / 'caldera-runtime-requirements.txt').read_text())}
    roots = runtime.active_requirements(runtime.requirement_rows(
        (SHARED / 'caldera-runtime-requirements.in').read_text()),
        {'python_version': '3.10', 'extra': ''})
    for requirement in roots:
        package = packages[runtime.canonicalize_name(requirement.name)]
        assert requirement.specifier.contains(package.version, prereleases=True)
        assert package.hashes


def test_provisioner_checks_lock_before_starting_server():
    source = (SHARED / 'caldera.sh').read_text()
    assert '--require-hashes' in source
    assert source.index('python3 /tmp/caldera_runtime_lock.py') < source.index('systemctl restart caldera')
