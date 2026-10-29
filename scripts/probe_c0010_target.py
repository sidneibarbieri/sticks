"""Observe the bounded C0010 transfer and SUT fixtures inside its target VM."""

import hashlib
import json
import os
from pathlib import Path
import socket
import stat
from contextlib import ExitStack


EXPECTED_PAYLOAD = b"#!/bin/sh\necho STICKS benign payload\n"
EXPECTED_NOTICE = b"Synthetic shipping operations notice for C0010."
EXPECTED_PAGE = b"<html><body><h1>Israeli Shipping Login</h1></body></html>"


def read_regular(
    root: Path, relative_path: str, maximum_bytes: int
) -> tuple[bytes, int]:
    components = relative_path.split("/")
    with ExitStack() as opened:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        opened.callback(os.close, directory)
        for component in components[:-1]:
            directory = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory,
            )
            opened.callback(os.close, directory)
        descriptor = os.open(
            components[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory,
        )
        opened.callback(os.close, descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or not 0 < metadata.st_size <= maximum_bytes
        ):
            raise ValueError(f"Missing or invalid guest fixture: {components[-1]}")
        content = os.read(descriptor, maximum_bytes + 1)
        if len(content) != metadata.st_size:
            raise ValueError("Guest fixture changed during observation")
        return content, metadata.st_mode


def collect_fixture_readiness(root: Path) -> dict[str, bool]:
    """Read declared profile fixtures without requiring any campaign effect."""
    notice, _ = read_regular(root, "home/ubuntu/shipping_notice.txt", 65536)
    page, _ = read_regular(root, "var/www/html/index.html", 65536)
    return {"notice_matches": notice == EXPECTED_NOTICE,
            "page_matches": page == EXPECTED_PAGE}


def collect_observation(root: Path) -> dict:
    source, _ = read_regular(root, "tmp/sticks_t1105/payload.sh", 4096)
    downloaded, downloaded_mode = read_regular(
        root, "tmp/sticks_downloaded_payload.sh", 4096
    )
    server_log, _ = read_regular(root, "tmp/sticks_t1105_server.log", 65536)
    notice, _ = read_regular(root, "home/ubuntu/shipping_notice.txt", 65536)
    page, _ = read_regular(root, "var/www/html/index.html", 65536)
    checks = {
        "declared_notice_present": notice == EXPECTED_NOTICE,
        "declared_page_present": page == EXPECTED_PAGE,
        "transfer_matches_source": source == downloaded == EXPECTED_PAYLOAD,
        "http_get_recorded": b'"GET /payload.sh HTTP/1.1" 200' in server_log,
        "download_executable": bool(downloaded_mode & stat.S_IXUSR),
    }
    return {
        "schema": "c0010-target-transfer-observation/v1",
        "hostname": socket.gethostname(),
        "observer_uid": os.geteuid(),
        "boot_id": (root / "proc/sys/kernel/random/boot_id").read_text().strip(),
        "payload_sha256": hashlib.sha256(downloaded).hexdigest(),
        "checks": checks,
        "passed": all(checks.values()),
        "scope": "Target fixture and benign transfer only; watering-hole visit was local to "
        "the executor, not a target-browser effect or historical intrusion replay.",
    }


def main() -> int:
    observation = collect_observation(Path("/"))
    print(json.dumps(observation, sort_keys=True))
    return 0 if observation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
