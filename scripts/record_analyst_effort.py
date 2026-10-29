#!/usr/bin/env python3
"""Record preregistered analyst-effort trials without collecting identity or free text."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evaluation.effort_trial import (  # noqa: E402
    Condition,
    EffortTrial,
    EventKind,
    TrialEvent,
    active_seconds,
    read_trial,
    sha256,
    utc_now,
    write_trial,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--record", type=Path, required=True)
    start.add_argument("--trial-id", required=True)
    start.add_argument("--operator-code", required=True)
    start.add_argument("--condition", choices=[item.value for item in Condition], required=True)
    start.add_argument("--campaign-id", required=True)
    start.add_argument("--input", type=Path, required=True)
    for command in ("pause", "resume"):
        action = sub.add_parser(command)
        action.add_argument("--record", type=Path, required=True)
    finish = sub.add_parser("finish")
    finish.add_argument("--record", type=Path, required=True)
    finish.add_argument("--output", type=Path, required=True)
    finish.add_argument("--completed-steps", type=int, required=True)
    finish.add_argument("--unresolved-steps", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = utc_now()
    if args.command == "start":
        if args.record.exists():
            raise SystemExit(f"refusing to overwrite trial record: {args.record}")
        trial = EffortTrial(
            trial_id=args.trial_id,
            operator_code=args.operator_code,
            condition=Condition(args.condition),
            campaign_id=args.campaign_id,
            input_path=str(args.input),
            input_sha256=sha256(args.input),
            events=[TrialEvent(kind=EventKind.START, at_utc=now)],
        )
    else:
        trial = read_trial(args.record)
        kind = EventKind(args.command)
        events = [*trial.events, TrialEvent(kind=kind, at_utc=now)]
        updates: dict[str, object] = {"events": events}
        if kind is EventKind.FINISH:
            updates |= {
                "output_path": str(args.output),
                "output_sha256": sha256(args.output),
                "completed_steps": args.completed_steps,
                "unresolved_steps": args.unresolved_steps,
                "active_seconds": active_seconds(events),
            }
        trial = EffortTrial.model_validate(trial.model_dump() | updates)
    write_trial(args.record, trial)
    print(args.record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
