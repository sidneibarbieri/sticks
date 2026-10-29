"""Profile readiness must stop execution on absent fixtures or guest drift."""

import json
import subprocess

import pytest

from runners import c0010_guest_observer
from runners.capability_facts import FactScope


def scope():
    return FactScope(run_id='test-run', environment_id='test-lab', epoch='test-boot',
                     locus='target', host_id='target-linux-1', principal='ubuntu')


@pytest.mark.parametrize('changes', [{}, {'notice_matches': False}, {'boot_id': 'another-boot'}])
def test_fixture_readiness_requires_matching_guest_and_both_files(monkeypatch, changes):
    reply = {'hostname': 'target-linux-1', 'principal': 'ubuntu', 'observer_uid': 1000,
             'boot_id': 'test-boot', 'nonce': 'test-nonce',
             'notice_matches': True, 'page_matches': True} | changes
    monkeypatch.setattr(c0010_guest_observer, 'run_bash_on_target_vm',
                        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, json.dumps(reply), ''))
    if changes:
        with pytest.raises(ValueError, match='readiness'):
            c0010_guest_observer.require_c0010_fixture_readiness(scope(), 'test-nonce')
    else:
        result = c0010_guest_observer.require_c0010_fixture_readiness(scope(), 'test-nonce')
        assert result.notice_matches and result.page_matches
        assert result.boot_id == 'test-boot'


def test_fixture_readiness_propagates_failed_guest_probe(monkeypatch):
    monkeypatch.setattr(c0010_guest_observer, 'run_bash_on_target_vm',
                        lambda *args, **kwargs: subprocess.CompletedProcess([], 1, '', 'missing fixture'))
    with pytest.raises(subprocess.CalledProcessError):
        c0010_guest_observer.require_c0010_fixture_readiness(scope(), 'test-nonce')
