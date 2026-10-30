"""Verify retained dispatch consistency and campaign observation boot binding."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runners.caldera_session import CalderaSession
from runners.caldera_campaign_support import SUPPORTED_CALDERA_CAMPAIGNS
from runners.recorded_caldera_dispatch import replay_completed_command
from runners.runtime_campaign_report import parse_retained_campaign_report


def verify_journal(evidence: Path) -> dict[str, object]:
    session = CalderaSession.model_validate_json((evidence / "caldera-session.json").read_bytes())
    reports = list((evidence / "runtime-v2").glob("*/summary.json"))
    if len(reports) != 1:
        raise ValueError("Expected exactly one runtime campaign report")
    report = parse_retained_campaign_report(reports[0].read_text())
    if report.campaign_id not in SUPPORTED_CALDERA_CAMPAIGNS:
        raise ValueError("Campaign has no reviewed CALDERA journal scope")
    if any(step.status not in {"observed", "simulated"} for step in report.steps):
        raise ValueError("Campaign contains an incomplete or failed occurrence")
    directories = sorted((evidence / "caldera-dispatch").glob("command-*"))
    if not directories:
        raise ValueError("No retained CALDERA commands")
    results = [replay_completed_command(directory) for directory in directories]
    links = set()
    for result in results:
        dispatch = result.dispatch
        for field in ("operation_id", "group", "agent_id", "host", "principal", "platform", "executor"):
            if getattr(dispatch, field) != getattr(session.binding, field):
                raise ValueError("Retained command differs from session: " + field)
        if dispatch.link_id in links:
            raise ValueError("Repeated CALDERA link identity")
        links.add(dispatch.link_id)
    observed = [step for step in report.steps if step.status == "observed"]
    target_observed = [step for step in observed if step.contract.scope.locus == "target"]
    controller_observed = [step for step in observed if step.contract.scope.locus == "controller"]
    if len(target_observed) + len(controller_observed) != len(observed):
        raise ValueError("Observed occurrence has no reviewed execution locus")
    if len(results) != len(target_observed):
        raise ValueError("Native command count differs from observed target occurrence count")
    for step in target_observed:
        if step.outcome is None or not step.outcome.observations:
            raise ValueError("Observed occurrence has no predicate observations")
        for observation in step.outcome.observations:
            if (not observation.passed or observation.scope.epoch != str(session.target_boot_id)
                    or observation.scope.host_id != session.binding.host):
                raise ValueError("Observation differs from the session target boot")
    return {
        "schema": "caldera-journal-consistency/v1", "commands": len(results),
        "observed": len(observed), "simulated": report.simulated,
        "observed_target": len(target_observed),
        "observed_controller": len(controller_observed),
        "scope": "Retained journal consistency and boot binding; not native-server replay or historical fidelity",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    print(json.dumps(verify_journal(parser.parse_args().evidence), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
