"""Read-only, fixed-path controller observations for bounded C0010 staging."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import stat
from contextlib import ExitStack
from pathlib import Path

_MAX_FILE_BYTES = 65536
_SPEC_PATH = (
    Path(__file__).resolve().parents[1] / "data/observer_specs/c0010_controller.json"
)


def _load_expected_files(source: bytes) -> dict[str, dict[str, bytes]]:
    specification = json.loads(source)
    if specification["schema_version"] != "c0010-controller-spec/v1":
        raise ValueError("Unsupported C0010 controller specification")
    expected: dict[str, dict[str, bytes]] = {}
    for predicate in specification["predicates"]:
        files: dict[str, bytes] = {}
        for entry in predicate["files"]:
            path = entry["path"]
            components = path.split("/")
            if (
                not path.startswith("data/artifacts/")
                or any(component in {"", ".", ".."} for component in components)
                or path in files
            ):
                raise ValueError("Unsafe or duplicate controller observation path")
            files[path] = entry["utf8"].encode("utf-8")
        predicate_id = predicate["predicate_id"]
        if predicate_id in expected or not files:
            raise ValueError("Duplicate or empty controller observation predicate")
        expected[predicate_id] = files
    return expected


_SPEC_BYTES = _SPEC_PATH.read_bytes()
_EXPECTED_FILES = _load_expected_files(_SPEC_BYTES)


def _read_regular(root: Path, relative_path: str) -> bytes:
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
            or not 0 < metadata.st_size <= _MAX_FILE_BYTES
        ):
            raise ValueError(
                "Controller staging artifact is not a bounded regular file"
            )
        content = os.read(descriptor, _MAX_FILE_BYTES + 1)
        if len(content) != metadata.st_size:
            raise ValueError("Controller staging artifact changed during observation")
        return content


def measure(root: Path, predicate_id: str, run_id: str, nonce: str) -> dict:
    """Measure only the code-owned paths assigned to one literal predicate."""
    expected_files = _EXPECTED_FILES[predicate_id]
    observed = {path: _read_regular(root, path) for path in expected_files}
    digests = {
        path: hashlib.sha256(content).hexdigest() for path, content in observed.items()
    }
    encoded = json.dumps(digests, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": "c0010-controller-probe/v1",
        "predicate_id": predicate_id,
        "run_id": run_id,
        "nonce": nonce,
        "hostname": socket.gethostname(),
        "uid": os.geteuid(),
        "passed": observed == expected_files,
        "content_sha256": hashlib.sha256(encoded).hexdigest(),
        "file_sha256": [
            {"path": path, "sha256": digest} for path, digest in sorted(digests.items())
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--predicate", choices=tuple(_EXPECTED_FILES), required=True)
    parser.add_argument("--spec-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--nonce", required=True)
    arguments = parser.parse_args()
    if hashlib.sha256(_SPEC_BYTES).hexdigest() != arguments.spec_sha256:
        raise ValueError("C0010 controller specification differs from reviewed bytes")
    print(
        json.dumps(
            measure(
                arguments.root, arguments.predicate, arguments.run_id, arguments.nonce
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
