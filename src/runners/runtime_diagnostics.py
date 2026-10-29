"""Preserve process diagnostics without replacing the original exception."""

import subprocess
import hashlib
from typing import Annotated, Callable, TypeVar

from pydantic import Field

from runners.capability_facts import ImmutableRecord, Digest

Reply = TypeVar("Reply")


class ProcessFailure(ImmutableRecord):
    returncode: Annotated[int, Field(strict=True)] | None
    stdout: str
    stderr: str
    timed_out: Annotated[bool, Field(strict=True)]
    stdout_bytes: Annotated[int, Field(strict=True, ge=0)]
    stderr_bytes: Annotated[int, Field(strict=True, ge=0)]
    stdout_sha256: Digest
    stderr_sha256: Digest
    stdout_truncated: Annotated[bool, Field(strict=True)]
    stderr_truncated: Annotated[bool, Field(strict=True)]


def _text(stream: str | bytes | None) -> str:
    if isinstance(stream, bytes):
        return stream.decode("utf-8", errors="backslashreplace")
    return stream if stream is not None else ""


def _stream_fields(name: str, stream: str | bytes | None) -> dict:
    raw = stream if isinstance(stream, bytes) else _text(stream).encode("utf-8")
    representation = _text(stream).encode("utf-8")
    return {
        name: representation[:8192].decode("utf-8", errors="ignore"),
        f"{name}_bytes": len(raw),
        f"{name}_sha256": hashlib.sha256(raw).hexdigest(),
        f"{name}_truncated": len(representation) > 8192,
    }


def _diagnostic(
    returncode: int | None,
    stdout: str | bytes | None,
    stderr: str | bytes | None,
    *,
    timed_out: bool,
) -> ProcessFailure:
    return ProcessFailure(
        returncode=returncode,
        timed_out=timed_out,
        **_stream_fields("stdout", stdout),
        **_stream_fields("stderr", stderr),
    )


def process_failure(error: Exception | None) -> ProcessFailure | None:
    """Extract subprocess fields; callers still raise the same error."""
    retained = getattr(error, "_runtime_process_failure", None)
    if isinstance(retained, ProcessFailure):
        return retained
    if not isinstance(
        error, (subprocess.CalledProcessError, subprocess.TimeoutExpired)
    ):
        return None
    timed_out = isinstance(error, subprocess.TimeoutExpired)
    return _diagnostic(
        None if timed_out else error.returncode,
        error.stdout,
        error.stderr,
        timed_out=timed_out,
    )


def parse_guest_reply(
    result: subprocess.CompletedProcess,
    parser: Callable[[str], Reply],
    *,
    maximum_bytes: int = 8192,
) -> Reply:
    """Attach transport fields to parse errors, then raise them unchanged."""
    try:
        if len(result.stdout.encode("utf-8")) > maximum_bytes:
            raise ValueError("Guest reply exceeds its bounded size")
        return parser(result.stdout)
    except ValueError as error:
        error._runtime_process_failure = _diagnostic(
            result.returncode, result.stdout, result.stderr, timed_out=False
        )
        raise
