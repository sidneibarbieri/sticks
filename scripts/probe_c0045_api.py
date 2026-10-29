"""Observe responses from the declared loopback Ray-like laboratory fixture."""

import json
import os
import pwd
import socket
from pathlib import Path
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

MAX_RESPONSE_BYTES = 4096
HTTP_TIMEOUT_SECONDS = 3
API_BASE_URL = 'http://127.0.0.1:8265'


class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise ValueError('API probe refuses HTTP redirects')


def read_response(path: str) -> str:
    if path not in {'/api/version','/api/jobs/'}:
        raise ValueError('API probe path is not declared')
    opener = build_opener(ProxyHandler({}),RejectRedirect())
    with opener.open(API_BASE_URL + path,timeout=HTTP_TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise ValueError('API probe requires HTTP 200')
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError('API response exceeds its size bound')
    return content.decode('utf-8')


def responses_match(version_body: str, jobs_body: str) -> bool:
    if any(len(body.encode('utf-8')) > MAX_RESPONSE_BYTES for body in (version_body,jobs_body)):
        raise ValueError('API response exceeds its size bound')
    version, jobs = json.loads(version_body), json.loads(jobs_body)
    return (isinstance(version,dict) and isinstance(jobs,dict)
        and version.get('service') == 'ray-dashboard'
        and isinstance(version.get('version'),str) and bool(version['version'])
        and jobs.get('auth') == 'disabled' and isinstance(jobs.get('jobs'),list))


def collect_observation(nonce: str) -> dict:
    version_body = read_response('/api/version')
    jobs_body = read_response('/api/jobs/')
    return {'hostname':socket.gethostname(),'principal':pwd.getpwuid(os.geteuid()).pw_name,
        'observer_uid':os.geteuid(),
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'nonce':nonce,'version_body':version_body,'jobs_body':jobs_body,
        'passed':responses_match(version_body,jobs_body)}
