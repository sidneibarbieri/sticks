"""Host-side contract for the bounded C0045 retained fixtures."""

import hashlib
import re
from types import MappingProxyType

MAX_FIXTURE_BYTES = 262144
TRANSFER_PAYLOAD = (
    b'#!/bin/bash\necho "Network Reconnaissance Tool"\n'
    b'echo "Target: ${1:-127.0.0.1}"\n'
    b'echo "Mode: ${2:-ping}"\n'
)
TRANSFER_SHA256 = hashlib.sha256(TRANSFER_PAYLOAD).hexdigest()
TOOLKIT_SHA256 = MappingProxyType(
    {
        "port_scanner.py": "83a2ca4b1764db5f4456b5f5fc017be6967e1af0b256a57ca014e3d68d884c0c",
        "service_enum.sh": "82debdb73005a09027938daa32a4ffb01daf21b2190160c5f1f8927ac71365bf",
        "sys_profiler.py": "2259202e3c6dd7864d660be26dc9696135e54ac8962f134f2758a9c5663746c7",
    }
)


def execution_trace_path(nonce: str) -> str:
    """Return the bounded target trace path for a validated nonce."""
    if re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
        raise ValueError("Invalid trace acquisition nonce")
    return "/tmp/sticks-c0045-exec-" + nonce + ".trace"
