"""Controller staging checks must be fixed-path and independent of executor output."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


PROBE = Path(__file__).resolve().parents[1] / "scripts/probe_c0010_controller.py"
SPEC = Path(__file__).resolve().parents[1] / "data/observer_specs/c0010_controller.json"


def _probe(root: Path, predicate: str) -> dict:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(PROBE),
            "--root",
            str(root),
            "--predicate",
            predicate,
            "--spec-sha256",
            hashlib.sha256(SPEC.read_bytes()).hexdigest(),
            "--run-id",
            "run-synthetic",
            "--nonce",
            "challenge-synthetic",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def _stage(root: Path, relative_path: str, content: bytes) -> Path:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


@pytest.mark.parametrize(
    ("predicate", "files"),
    [
        (
            "payload-staged",
            {
                "data/artifacts/staging/benign_payload.bin": b"#!/bin/sh\necho 'STICKS controlled payload artifact'\n",
            },
        ),
        (
            "watering-hole-staged",
            {
                "data/artifacts/0.c0010_watering_hole/index.html": b'<html><body><h1>Israeli Shipping Login</h1><script src="/exploit.js"></script></body></html>\n',
                "data/artifacts/0.c0010_watering_hole/exploit.js": b"console.log('STICKS benign drive-by profile script');\n",
            },
        ),
        (
            "tool-staged",
            {
                "data/artifacts/staging/0.c0010_tool.sh": b"#!/bin/sh\necho 'STICKS benign staged tool'\n",
            },
        ),
    ],
)
def test_probe_measures_declared_controller_bytes(
    tmp_path: Path,
    predicate: str,
    files: dict[str, bytes],
) -> None:
    for relative_path, content in files.items():
        _stage(tmp_path, relative_path, content)

    result = _probe(tmp_path, predicate)

    assert result["passed"] is True
    assert result["run_id"] == "run-synthetic"
    assert result["nonce"] == "challenge-synthetic"
    assert result["predicate_id"] == predicate
    assert {entry["path"] for entry in result["file_sha256"]} == set(files)


def test_probe_reports_changed_bytes_as_failed(tmp_path: Path) -> None:
    _stage(tmp_path, "data/artifacts/staging/benign_payload.bin", b"wrong bytes")

    assert _probe(tmp_path, "payload-staged")["passed"] is False


def test_probe_refuses_symlinked_staging_file(tmp_path: Path) -> None:
    source = _stage(tmp_path, "other/payload.bin", b"wrong bytes")
    target = tmp_path / "data/artifacts/staging/benign_payload.bin"
    target.parent.mkdir(parents=True)
    target.symlink_to(source)

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(PROBE),
            "--root",
            str(tmp_path),
            "--predicate",
            "payload-staged",
            "--spec-sha256",
            hashlib.sha256(SPEC.read_bytes()).hexdigest(),
            "--run-id",
            "run-synthetic",
            "--nonce",
            "challenge-synthetic",
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert not completed.stdout


def test_probe_rejects_unreviewed_spec_digest(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(PROBE),
            "--root",
            str(tmp_path),
            "--predicate",
            "payload-staged",
            "--spec-sha256",
            "0" * 64,
            "--run-id",
            "run-synthetic",
            "--nonce",
            "challenge-synthetic",
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert not completed.stdout
