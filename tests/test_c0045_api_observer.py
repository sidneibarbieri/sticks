"""Only scoped fixture responses may establish the C0045 API observation."""

import json
import subprocess

import pytest
from pydantic import ValidationError

from runners import c0045_api_observer
from runners.capability_authority import (
    acquire_registered_observation,
    verify_registered_observation,
)
from runners.capability_facts import FactScope


def request():
    return c0045_api_observer.C0045ApiRequest(sut_profile_id='0.shadowray',nonce='test-nonce',
        scope=FactScope(run_id='test-run',environment_id='test-lab',epoch='test-boot',
            locus='target',host_id='target-linux-1',principal='rayuser'),producer_occurrence=1)


def response(**changes):
    return {'hostname':'target-linux-1','principal':'rayuser','observer_uid':1001,
        'boot_id':'test-boot','nonce':'test-nonce','version_body':'{"version":"2.9.0","service":"ray-dashboard"}',
        'jobs_body':'{"auth":"disabled","jobs":[]}', 'passed':True} | changes


@pytest.mark.parametrize('changes', [
    {'boot_id':'other-boot'}, {'nonce':'other-nonce'}, {'principal':'ubuntu'},
    {'hostname':'controller'}, {'jobs_body':'{"auth":"enabled","jobs":[]}'},
])
def test_guest_identity_or_payload_drift_does_not_grant_product(monkeypatch, changes):
    monkeypatch.setattr(c0045_api_observer,'run_bash_on_target_vm',
        lambda *args,**kwargs:subprocess.CompletedProcess([],0,json.dumps(response(**changes)),''))
    observed = c0045_api_observer.observe_c0045_api(request())
    assert not observed.passed
    assert observed.established_facts == ()


def test_guest_passed_flag_is_not_a_trust_boundary(monkeypatch):
    monkeypatch.setattr(c0045_api_observer, 'run_bash_on_target_vm',
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(response(passed=False)), ''))
    observed = c0045_api_observer.observe_c0045_api(request())
    assert observed.passed
    assert observed.established_facts == ('service:ray_fixture_responses',)


def test_registered_observation_grants_service_fact_not_shell(monkeypatch,tmp_path):
    monkeypatch.setattr(c0045_api_observer,'run_bash_on_target_vm',
        lambda *args,**kwargs:subprocess.CompletedProcess([],0,json.dumps(response()),''))
    selected = request()
    reference = acquire_registered_observation('c0045-api',selected,run_root=tmp_path)
    observed = verify_registered_observation(reference,run_root=tmp_path,
        expected_scope=selected.scope,expected_predicate='ray-fixture-api')
    assert observed.passed
    assert observed.established_facts == ('service:ray_fixture_responses',)
    assert observed.producer_occurrence == 1


def test_transport_failure_remains_an_error(monkeypatch):
    monkeypatch.setattr(c0045_api_observer,'run_bash_on_target_vm',
        lambda *args,**kwargs:subprocess.CompletedProcess([],9,'','original failure'))
    with pytest.raises(subprocess.CalledProcessError):
        c0045_api_observer.observe_c0045_api(request())


@pytest.mark.parametrize('occurrence',[True,'1',2])
def test_occurrence_identity_is_an_exact_integer(occurrence):
    fields = request().model_dump()
    fields['producer_occurrence'] = occurrence
    with pytest.raises(ValidationError):
        c0045_api_observer.C0045ApiRequest.model_validate(fields)
