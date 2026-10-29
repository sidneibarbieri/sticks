"""Reviewed command bytes and bounded claims for two C0045 occurrences."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import StringConstraints

TraceKind = Literal["python", "network"]
TraceNonce = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{32}$")]


@dataclass(frozen=True)
class ReadonlyCommandSpec:
    occurrence: int
    predicate_id: str
    product: str
    script: str


_COMMANDS = MappingProxyType(
    {
        "python": ReadonlyCommandSpec(
            7,
            "python-execution-trace",
            "execution:python_interpreter_observed",
            """
set -e
cd -- "$HOME"
python3 - <<'PY'
import os
import platform
import socket
import sys

print(f"Python version: {sys.version}")
print(f"Platform: {platform.platform()}")
print(f"User: {os.getenv('USER', 'unknown')}")
print(f"Home: {os.getenv('HOME', 'unknown')}")
print(f"Hostname: {socket.gethostname()}")
print()
print("Current directory contents:")
for item in sorted(os.listdir('.')):
    print(f"  {item}")
PY
""",
        ),
        "network": ReadonlyCommandSpec(
            8,
            "network-query-trace",
            "discovery:kernel_queries_observed",
            """
set -euo pipefail
ip -json address show
ip -json route show
printf '[network-target] %s\\n' "$(hostname)"
""",
        ),
    }
)


def command_spec(kind: TraceKind) -> ReadonlyCommandSpec:
    if kind not in _COMMANDS:
        raise ValueError("Unknown reviewed C0045 command")
    return _COMMANDS[kind]
