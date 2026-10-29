"""Host-side validation contract for the bounded C0045 API fixture."""

import json

MAX_RESPONSE_BYTES = 4096


def responses_match(version_body: str, jobs_body: str) -> bool:
    """Validate both bounded fixture responses without trusting guest verdicts."""
    if any(
        len(body.encode("utf-8")) > MAX_RESPONSE_BYTES
        for body in (version_body, jobs_body)
    ):
        raise ValueError("API response exceeds its size bound")
    version = json.loads(version_body)
    jobs = json.loads(jobs_body)
    return (
        isinstance(version, dict)
        and isinstance(jobs, dict)
        and version.get("service") == "ray-dashboard"
        and isinstance(version.get("version"), str)
        and bool(version["version"])
        and jobs.get("auth") == "disabled"
        and isinstance(jobs.get("jobs"), list)
    )
