"""The Ray-like fixture predicate cannot infer access from arbitrary JSON."""

import pytest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts import probe_c0045_api


VERSION = '{"version":"2.9.0","service":"ray-dashboard"}'
JOBS = '{"jobs":[],"auth":"disabled"}'


def test_declared_api_responses_pass():
    assert probe_c0045_api.responses_match(VERSION, JOBS)


@pytest.mark.parametrize('version,jobs', [
    ('{"service":"other"}', JOBS),
    (VERSION, '{"auth":"disabled"}'),
    (VERSION, '{"auth":"enabled","jobs":[]}'),
    (VERSION, '{"auth":"disabled","jobs":{}}'),
])
def test_wrong_service_or_job_shape_does_not_pass(version, jobs):
    assert not probe_c0045_api.responses_match(version, jobs)


def test_response_size_limit_is_not_silently_truncated():
    with pytest.raises(ValueError, match='size'):
        probe_c0045_api.responses_match(' ' * 4097, JOBS)


def test_malformed_json_is_not_converted_to_service_evidence():
    with pytest.raises(ValueError):
        probe_c0045_api.responses_match('not json', JOBS)


def test_collector_retains_actual_response_bodies_and_challenge(monkeypatch,tmp_path):
    boot = tmp_path/'boot-id'
    boot.write_text('test-boot\n')
    monkeypatch.setattr(probe_c0045_api,'Path',lambda path:boot)
    responses = {'/api/version':VERSION,'/api/jobs/':JOBS}
    monkeypatch.setattr(probe_c0045_api,'read_response',responses.__getitem__)
    result = probe_c0045_api.collect_observation('test-nonce')
    assert result['nonce'] == 'test-nonce'
    assert result['boot_id'] == 'test-boot'
    assert result['version_body'] == VERSION and result['jobs_body'] == JOBS
    assert result['passed']


@pytest.mark.parametrize('redirect', [False, True])
def test_response_reader_uses_bounded_local_http_without_redirect(monkeypatch, redirect):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            self.send_response(302 if redirect else 200)
            if redirect:
                self.send_header('Location','/redirected')
            self.end_headers()
            self.wfile.write(VERSION.encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(probe_c0045_api,'API_BASE_URL',f'http://127.0.0.1:{server.server_port}')
        if redirect:
            with pytest.raises(ValueError,match='redirect'):
                probe_c0045_api.read_response('/api/version')
        else:
            assert probe_c0045_api.read_response('/api/version') == VERSION
        assert calls == ['/api/version']
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
