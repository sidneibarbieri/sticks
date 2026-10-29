"""Keep each Stage-2 authoring run apart from the frozen evidence it extends.

The frozen run behind the paper's reach numbers lives in fixed directories. A new
run never writes there: it gets its own directory, named by a run id, holding the
manifest, the raw provider calls, the admitted drafts, one decision per attempted
technique and a summary. Consumers of the frozen evidence therefore cannot pick up
an experimental run by accident.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class OutcomeStatus(str, Enum):
    admitted = "admitted"
    rejected = "rejected"
    provider_failure = "provider_failure"


class TechniqueDecision(BaseModel):
    """What happened to one attempted technique in a run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    technique_id: str
    corpus_steps: int = Field(ge=0)
    status: OutcomeStatus
    rejection_code: str | None = None
    detail: str = ""


class ProposerSettings(BaseModel):
    """Provider parameters that shape the proposals; never the endpoint or the key."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model: str
    temperature: float
    max_output_tokens: int
    timeout_seconds: int
    max_requests: int
    max_estimated_usd: float


class FrozenBaseline(BaseModel):
    """The frozen evidence a run extends, recorded so the run can be compared with it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trusted_techniques: int
    frozen_draft_techniques: int
    frozen_reach_steps: int
    total_steps: int


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    started_at: str
    source_commit: str | None
    source_tree_dirty: bool | None
    proposer: ProposerSettings
    baseline: FrozenBaseline
    target_techniques: list[str]


class AuthoringRun:
    """The directory layout of one isolated authoring run."""

    def __init__(self, runs_root: Path, run_id: str) -> None:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError(f"run id must match {RUN_ID_PATTERN.pattern}: {run_id!r}")
        if runs_root.is_symlink():
            raise ValueError("authoring runs root must not be a symlink")
        self.runs_root = runs_root
        self.run_id = run_id
        self.root = runs_root / run_id

    @property
    def calls(self) -> Path:
        return self.root / "calls"

    @property
    def drafts(self) -> Path:
        return self.root / "drafts"

    @property
    def decisions(self) -> Path:
        return self.root / "decisions.jsonl"

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def summary(self) -> Path:
        return self.root / "summary.json"

    def create(self, manifest: RunManifest) -> None:
        """Create the run directory; an existing run is never overwritten."""
        if self.runs_root.is_symlink():
            raise ValueError("authoring runs root must not be a symlink")
        self.root.mkdir(parents=True, exist_ok=False)
        self.calls.mkdir()
        self.drafts.mkdir()
        self.decisions.touch()
        _write_json(self.manifest, manifest.model_dump(mode="json"))

    def record(self, decision: TechniqueDecision) -> None:
        with self.decisions.open("a", encoding="utf-8") as handle:
            handle.write(decision.model_dump_json() + "\n")

    def write_draft(self, technique_id: str, draft: dict[str, object]) -> None:
        _write_json(self.drafts / f"{technique_id.replace('.', '_')}.json", draft)

    def write_summary(self, summary: dict[str, object]) -> None:
        _write_json(self.summary, summary)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def source_revision(project_root: Path) -> tuple[str | None, bool | None]:
    """Return the commit and dirty flag, or (None, None) outside a git checkout."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True
    )
    if head.returncode != 0:
        return None, None
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "."],
        cwd=project_root, capture_output=True, text=True, check=True,
    )
    return head.stdout.strip(), bool(status.stdout.strip())


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
