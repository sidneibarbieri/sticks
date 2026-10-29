"""Bind retained host-location verdicts to the exact execution summary."""

from __future__ import annotations


def bound_host_leakage_audit(audit: dict, summary: dict | None) -> tuple[bool | None, str]:
    """Use an audit only when it names the current retained summary and its bytes."""
    if not audit:
        return None, "not_assessed"
    if summary is None:
        return None, "execution_unavailable"
    if audit.get("latest_summary") != summary["summary_path"]:
        return None, "different_summary"
    if audit.get("summary_sha256") != summary["summary_sha256"]:
        return None, "unverified_summary_digest"
    detected = audit.get("host_leakage_detected")
    if not isinstance(detected, bool):
        raise ValueError("host-leakage audit verdict must be a boolean")
    return detected, "bound"
