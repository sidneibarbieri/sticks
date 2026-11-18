"""The root run.sh is the single reviewer entry point; each command delegates to one path."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_runtime(tmp_path):
    executable = tmp_path / "python-fixture"
    executable.write_text(r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
if sys.argv[1:2] in (['-c'], ['-']):
    raise SystemExit(0)
with Path(os.environ['STICKS_TEST_CALLS']).open('a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\n')
if os.environ.get('STICKS_TEST_FAIL') == sys.argv[1]:
    raise SystemExit(9)
""")
    executable.chmod(0o700)
    calls = tmp_path / "calls.jsonl"
    home = tmp_path / "home"
    home.mkdir()
    environment = {"PATH": os.environ["PATH"], "HOME": str(home),
                   "STICKS_PYTHON": str(executable), "STICKS_TEST_CALLS": str(calls)}
    return environment, calls, home


def front_door(environment, *arguments):
    return subprocess.run(["bash", "run.sh", *arguments], cwd=ROOT, env=environment,
                          capture_output=True, text=True)


def recorded(calls):
    return [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []


def test_help_lists_every_command_with_its_cost(fake_runtime):
    environment, calls, _ = fake_runtime
    result = front_door(environment)
    assert result.returncode == 0
    for command in ("demo", "review", "emulate", "doctor", "lab", "workbench", "all"):
        assert f"\n  {command}" in result.stdout
    assert not recorded(calls)


def test_unknown_command_is_refused_without_side_effects(fake_runtime):
    environment, calls, _ = fake_runtime
    assert front_door(environment, "deploy").returncode == 2
    assert not recorded(calls)


def test_emulate_defaults_to_a_covered_campaign(fake_runtime):
    environment, calls, _ = fake_runtime
    assert front_door(environment, "emulate").returncode == 0
    assert recorded(calls) == [["scripts/emulate.py", "C0045"]]


def test_lab_without_run_root_writes_outside_the_source_tree(fake_runtime):
    environment, calls, home = fake_runtime
    result = front_door(environment, "lab", "--campaign", "0.c0010")
    assert result.returncode == 0, result.stderr
    runner = recorded(calls)[1]
    assert runner[:3] == ["scripts/run_isolated_lab_campaign.py", "--campaign", "0.c0010"]
    run_root = Path(runner[runner.index("--run-root") + 1])
    assert run_root.parent == home / "sticks-runs"
    assert run_root.name.startswith("c0010-")


def test_all_does_not_start_the_lab_when_the_preflight_fails(fake_runtime):
    environment, calls, _ = fake_runtime
    environment["STICKS_TEST_FAIL"] = "scripts/doctor.py"
    result = front_door(environment, "all")
    assert result.returncode == 1
    scripts = [call[0] for call in recorded(calls)]
    assert "scripts/run_isolated_lab_campaign.py" not in scripts
    assert "failed:" in result.stdout and "doctor" in result.stdout
