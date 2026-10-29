"""A Stage-2 authoring run writes only to its own run directory."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from curation.authoring_run import AuthoringRun  # noqa: E402

FROZEN_PATHS = (
    PROJECT_ROOT / "release" / "experiments" / "stage2_authoring",
    PROJECT_ROOT / "data" / "concretization" / "proposed_templates",
    PROJECT_ROOT / "data" / "concretization" / "action_templates.json",
)
LOCAL_CONFIG = {
    "llm": {
        "provider": "openai",
        "model": "stub-model",
        "base_url": "http://localhost:11434",
        "api_key_env": "STUB_API_KEY",
        "budget": {"max_requests": 10},
    }
}


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "author_catalog_templates", PROJECT_ROOT / "scripts" / "author_catalog_templates.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fingerprint(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for root in paths:
        files = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
        for path in files:
            digest.update(str(path.relative_to(PROJECT_ROOT)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _valid_proposal(technique_id: str, vocabulary) -> str:
    effect = sorted(vocabulary.effect_predicates)[0]
    kind = sorted(vocabulary.bindable_kinds)[0]
    return json.dumps({
        "template_id": f"stub-{technique_id.lower().replace('.', '-')}",
        "technique_ids": [technique_id],
        "execution_domain": "target",
        "parameter_kinds": {"subject": kind},
        "requires": [],
        "produces": ["stub_state"],
        "evidence_predicates": [effect],
        "fidelity_ceiling": "inspired",
        "description": "Stub template for an isolation test.",
    })


def _run(script, tmp_path, monkeypatch, run_id: str, limit: int = 3) -> Path:
    config = tmp_path / "config.json"
    config.write_text(json.dumps(LOCAL_CONFIG))
    monkeypatch.setattr(script, "RUNS_ROOT", tmp_path / "runs")
    replies = iter(["valid", "prose", "network"])

    def stub_complete_raw(provider_config, *, system_prompt, user_prompt, output_dir, budget):
        technique_id = user_prompt.split("\n", 1)[0].removeprefix("Technique id: ")
        reply = next(replies)
        if reply == "network":
            raise TimeoutError("stubbed timeout")
        output_dir.mkdir(parents=True)
        vocabulary = script.AdmissionVocabulary(
            predicate_roles=script.load_roles(script.ROLES), bindable_kinds=script.bindable_kinds()
        )
        content = _valid_proposal(technique_id, vocabulary) if reply == "valid" else "I cannot."
        (output_dir / "provider_response.json").write_text(content)
        return content, None

    monkeypatch.setattr(script, "complete_raw", stub_complete_raw)
    monkeypatch.setenv("STUB_API_KEY", "local")
    assert script.main(["--config", str(config), "--run-id", run_id, "--limit", str(limit)]) == 0
    return tmp_path / "runs" / run_id


def test_a_run_leaves_the_frozen_evidence_byte_identical(tmp_path, monkeypatch):
    script = _load_script()
    before = _fingerprint(FROZEN_PATHS)
    _run(script, tmp_path, monkeypatch, "isolation-check")
    assert _fingerprint(FROZEN_PATHS) == before


def test_a_run_records_every_decision_and_its_provenance(tmp_path, monkeypatch):
    script = _load_script()
    run_root = _run(script, tmp_path, monkeypatch, "decisions-check")

    decisions = [json.loads(line) for line in (run_root / "decisions.jsonl").read_text().splitlines()]
    assert [decision["status"] for decision in decisions] == ["admitted", "rejected", "provider_failure"]
    assert decisions[1]["rejection_code"] == "malformed_schema"

    manifest = json.loads((run_root / "manifest.json").read_text())
    assert manifest["proposer"]["model"] == "stub-model"
    assert "base_url" not in manifest["proposer"]
    assert manifest["target_techniques"] == [decision["technique_id"] for decision in decisions]

    summary = json.loads((run_root / "summary.json").read_text())
    assert summary["admitted_templates"] == 1
    assert summary["provider_failures"] == 1
    assert summary["frozen_reach_steps"] == manifest["baseline"]["frozen_reach_steps"]
    assert summary["run_increment_steps"] == decisions[0]["corpus_steps"]

    (draft,) = (run_root / "drafts").glob("*.json")
    assert json.loads(draft.read_text())["provenance"]["run_id"] == "decisions-check"


def test_a_run_never_targets_a_technique_the_frozen_run_already_drafted(tmp_path, monkeypatch):
    script = _load_script()
    run_root = _run(script, tmp_path, monkeypatch, "targets-check")
    targets = set(json.loads((run_root / "manifest.json").read_text())["target_techniques"])
    assert not targets & script.frozen_draft_techniques()
    assert not targets & script.trusted_techniques()


def test_an_existing_run_is_never_overwritten(tmp_path, monkeypatch):
    script = _load_script()
    _run(script, tmp_path, monkeypatch, "repeat-check", limit=1)
    with pytest.raises(FileExistsError):
        _run(script, tmp_path, monkeypatch, "repeat-check", limit=1)


@pytest.mark.parametrize("run_id", ["", "../calls", "a/b", ".hidden"])
def test_a_run_id_cannot_escape_the_runs_directory(tmp_path, run_id):
    with pytest.raises(ValueError):
        AuthoringRun(tmp_path, run_id)


def test_a_symlinked_runs_root_is_rejected(tmp_path):
    frozen_root = tmp_path / "frozen"
    frozen_root.mkdir()
    runs_root = tmp_path / "runs"
    runs_root.symlink_to(frozen_root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        AuthoringRun(runs_root, "isolated-run")
    assert list(frozen_root.iterdir()) == []


def test_a_missing_credential_fails_before_any_run_directory_exists(tmp_path, monkeypatch):
    script = _load_script()
    config = tmp_path / "config.json"
    config.write_text(json.dumps(LOCAL_CONFIG))
    monkeypatch.setattr(script, "RUNS_ROOT", tmp_path / "runs")
    monkeypatch.delenv("STUB_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="STUB_API_KEY"):
        script.main(["--config", str(config), "--run-id", "no-credential"])
    assert not (tmp_path / "runs").exists()
