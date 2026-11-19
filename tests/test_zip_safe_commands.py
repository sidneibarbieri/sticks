"""Reviewer-facing commands must work from the anonymous ZIP, which drops executable bits."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOT_SLASH_SCRIPT = re.compile(r"(^|[^\w./])\./[\w-]+\.sh\b")
REVIEWER_FACING = ("run.sh", "artifact/run.sh", "README.md", "docs/reviewer_quickstart.md")


@pytest.mark.parametrize("relative_path", REVIEWER_FACING)
def test_reviewer_facing_text_never_relies_on_an_executable_bit(relative_path):
    lines = (ROOT / relative_path).read_text().splitlines()
    offending = [f"{number}: {line.strip()}" for number, line in enumerate(lines, 1)
                 if DOT_SLASH_SCRIPT.search(line)]
    assert not offending, "use 'bash script.sh' instead:\n" + "\n".join(offending)
