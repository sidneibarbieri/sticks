#!/usr/bin/env python3
"""Render paper macros from verified, scoped campaign outcomes."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.audit_typed_campaign_outcomes import CampaignOutcome, audit_runs


CAMPAIGN_LABELS = {"0.c0010": "Infrastructure", "0.c0026": "Collection"}


def render_tex(outcomes: list[CampaignOutcome]) -> str:
    by_campaign = {outcome.campaign_id: outcome for outcome in outcomes}
    if len(by_campaign) != len(outcomes) or set(by_campaign) != set(CAMPAIGN_LABELS):
        raise ValueError("Paper outcomes require exactly C0010 and C0026")
    source_hashes = {outcome.source_tree_sha256 for outcome in outcomes}
    if len(source_hashes) != 1:
        raise ValueError("Paper outcomes must share one source tree")
    lines = ["% Generated from verified, sealed QEMU run receipts."]
    for campaign_id, label in CAMPAIGN_LABELS.items():
        outcome = by_campaign[campaign_id]
        if outcome.total != (9 if campaign_id == "0.c0010" else 6):
            raise ValueError(f"Unexpected occurrence count for {campaign_id}")
        lines.append(f"% {campaign_id} receipt SHA-256: {outcome.receipt_sha256}")
        for suffix, count in (
            ("Total", outcome.total),
            ("Target", outcome.observed_target),
            ("Controller", outcome.observed_controller),
            ("Simulated", outcome.simulated),
            ("Failed", outcome.failed),
        ):
            lines.append(f"\\newcommand{{\\cold{label}{suffix}}}{{{count}}}")
    lines.append(f"% Shared source tree SHA-256: {next(iter(source_hashes))}")
    return "\n".join(lines) + "\n"


def render_caldera_tex(outcomes: list[CampaignOutcome]) -> str:
    """Render the C0026 cycle whose commands were dispatched through CALDERA."""
    if len(outcomes) != 1 or outcomes[0].campaign_id != "0.c0026":
        raise ValueError("CALDERA outcomes require exactly one C0026 run")
    outcome = outcomes[0]
    if outcome.total != 6:
        raise ValueError("Unexpected occurrence count for the CALDERA C0026 run")
    lines = [
        "% Generated from the verified, sealed C0026 receipt dispatched through CALDERA.",
        f"% 0.c0026 receipt SHA-256: {outcome.receipt_sha256}",
    ]
    for suffix, count in (
        ("Total", outcome.total),
        ("Target", outcome.observed_target),
        ("Controller", outcome.observed_controller),
        ("Simulated", outcome.simulated),
        ("Failed", outcome.failed),
    ):
        lines.append(f"\\newcommand{{\\caldera{suffix}}}{{{count}}}")
    lines.append(f"% Source tree SHA-256: {outcome.source_tree_sha256}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--series", choices=("qemu", "caldera"), default="qemu")
    args = parser.parse_args()
    renderer = render_caldera_tex if args.series == "caldera" else render_tex
    content = renderer(audit_runs(args.run_root))
    args.output.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
