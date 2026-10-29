#!/usr/bin/env python3
"""Apply the documented socket_vmnet fd transport to vagrant-qemu 0.6.3."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


PLUGIN_RELATIVE_PATH = Path(
    "lib/vagrant-qemu/network/socket_vmnet.rb"
)
STREAM_SELECTION = "options[:use_stream] = Network.qemu_supports_stream?(qemu_binary) != false"
FD_SELECTION = "options[:use_stream] = false"


def locate_plugin(vagrant_home: Path) -> Path:
    """Find one pinned provider source, rejecting ambiguous global installations."""
    candidates = sorted(
        vagrant_home.glob("gems/*/gems/vagrant-qemu-0.6.3")
    )
    if len(candidates) != 1:
        raise RuntimeError(
            "expected exactly one vagrant-qemu 0.6.3 installation; "
            f"found {len(candidates)}"
        )
    source_path = candidates[0] / PLUGIN_RELATIVE_PATH
    if not source_path.is_file():
        raise FileNotFoundError(f"vagrant-qemu transport source is absent: {source_path}")
    return source_path


def fixed_source(source: str) -> str:
    """Replace only the version-pinned transport-selection statement."""
    if FD_SELECTION in source:
        return source
    if source.count(STREAM_SELECTION) != 1:
        raise RuntimeError("unexpected vagrant-qemu socket_vmnet implementation")
    return source.replace(STREAM_SELECTION, FD_SELECTION)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vagrant-home",
        type=Path,
        default=Path(os.environ.get("VAGRANT_HOME", "~/.vagrant.d")).expanduser(),
    )
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    source_path = locate_plugin(options.vagrant_home)
    original = source_path.read_text(encoding="utf-8")
    fixed = fixed_source(original)
    if fixed != original and options.check:
        raise RuntimeError("vagrant-qemu still selects unsupported socket_vmnet stream transport")
    if fixed != original:
        source_path.write_text(fixed, encoding="utf-8")
    print("socket_vmnet transport: documented fd route")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
