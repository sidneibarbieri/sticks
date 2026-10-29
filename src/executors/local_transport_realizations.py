"""Local-substrate realizations of the T1105 transport templates.

These execute the three admissible Ingress Tool Transfer templates as real, distinct
transports on the local host, so the behavioral-substitution experiment can compare their
observed effects without the full lab. The substrate is local: filesystem effect, exit
code, and evidence-predicate satisfaction are observed; network and process telemetry and
detection are not instrumented here (they require the lab).

Each transport moves the same benign, hash-pinned payload to a destination by a genuinely
different mechanism -- a shell copy, a staged copy, and an HTTP transfer over loopback --
so the transport is the independent variable, not an artifact of the implementation. The
staging copy removes its intermediate file, so the end-state filesystem effect is
comparable across all three; the remaining difference is the transport mechanism, which is
observable only in telemetry the local substrate does not capture.
"""

from __future__ import annotations

import hashlib
import subprocess
import threading
import urllib.request
from dataclasses import dataclass, field
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BENIGN_PAYLOAD = b"sticks-benign-payload\n"


@dataclass
class TransferResult:
    exit_code: int
    destination_sha256: str
    created_files: list[str] = field(default_factory=list)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transfer_via_shell(payload: Path, destination: Path) -> TransferResult:
    """Direct shell copy: the payload is copied to the destination in one step."""
    completed = subprocess.run(["cp", str(payload), str(destination)], check=False)
    return TransferResult(
        exit_code=completed.returncode,
        destination_sha256=_sha256(destination),
        created_files=[destination.name],
    )


def transfer_via_staging(payload: Path, destination: Path) -> TransferResult:
    """Staged copy: the payload is staged, then delivered; the stage is then removed."""
    staging = destination.with_suffix(destination.suffix + ".staged")
    stage = subprocess.run(["cp", str(payload), str(staging)], check=False)
    deliver = subprocess.run(["cp", str(staging), str(destination)], check=False)
    staging.unlink()
    return TransferResult(
        exit_code=stage.returncode or deliver.returncode,
        destination_sha256=_sha256(destination),
        created_files=[destination.name],
    )


def transfer_via_loopback_channel(payload: Path, destination: Path) -> TransferResult:
    """HTTP transfer over loopback: the payload is served on 127.0.0.1 and downloaded."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(payload.parent))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/{payload.name}"
        urllib.request.urlretrieve(url, destination)
    finally:
        server.shutdown()
        thread.join()
    return TransferResult(
        exit_code=0,
        destination_sha256=_sha256(destination),
        created_files=[destination.name],
    )


REALIZATIONS = {
    "transfer-benign-payload": transfer_via_shell,
    "transfer-staged-benign-tool": transfer_via_staging,
    "transfer-over-resolved-lab-channel": transfer_via_loopback_channel,
}
