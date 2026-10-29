"""Measure C0010's bounded loopback HTTP service from a separate process."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import socket


_EXPECTED_BODIES = {
    "/index.html": (
        b'<html><body><h1>Israeli Shipping Login</h1><script src="/exploit.js"></script></body></html>\n'
    ),
    "/exploit.js": b"console.log('STICKS benign drive-by profile script');\n",
}


def measure(port: int, run_id: str, nonce: str) -> dict:
    """Fetch only the two literal paths from a loopback-bound lab server."""
    responses: dict[str, dict[str, int | str]] = {}
    for path, expected in _EXPECTED_BODIES.items():
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", path)
            reply = connection.getresponse()
            body = reply.read(65537)
            responses[path] = {
                "status": reply.status,
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "body_bytes": len(body),
            }
        finally:
            connection.close()
    return {
        "schema": "c0010-loopback-http-probe/v1",
        "run_id": run_id,
        "nonce": nonce,
        "hostname": socket.gethostname(),
        "uid": os.geteuid(),
        "port": port,
        "responses": [
            {"path": path, **measurement}
            for path, measurement in sorted(responses.items())
        ],
        "passed": all(
            responses[path]["status"] == 200
            and responses[path]["body_bytes"] == len(expected)
            and responses[path]["body_sha256"] == hashlib.sha256(expected).hexdigest()
            for path, expected in _EXPECTED_BODIES.items()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--nonce", required=True)
    arguments = parser.parse_args()
    if not 0 < arguments.port < 65536:
        raise ValueError("Invalid C0010 loopback port")
    print(json.dumps(measure(arguments.port, arguments.run_id, arguments.nonce)))


if __name__ == "__main__":
    main()
