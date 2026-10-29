"""Public runner path preserves typed outcomes and a complete denominator."""

import ast
import json
import shlex
import subprocess
import sys
import hashlib

from executors import executor_registry, legacy_parity_expansion_executors
from runners import (
    campaign_runner,
    lab_runtime_bootstrap,
    lab_bootstrap_observer,
    c0026_capability_observers,
)


def guest_fixture(
    monkeypatch, tmp_path, failed_predicate=None, altered_collection=False
):
    commands = []
    collection_checks = []

    def transport(sut_profile_id, bash_script, **options):
        assert sut_profile_id == "0.c0026"
        assert options["execution_user"] == "ubuntu"
        if bash_script.startswith("python3 -c "):
            code = shlex.split(bash_script)[2]
            fields = {
                keyword.arg: ast.literal_eval(keyword.value)
                for node in ast.walk(ast.parse(code))
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "dict"
                for keyword in node.keywords
                if keyword.arg in {"nonce", "predicate_id"}
            }
            result = dict(
                hostname="target-linux-1",
                principal="ubuntu",
                boot_id="boot-a",
                nonce=fields["nonce"],
            )
            if "predicate_id" in fields:
                if (
                    failed_predicate == "malformed_collection"
                    and fields["predicate_id"] == "collection-bytes"
                ):
                    return subprocess.CompletedProcess(
                        ["guest-fixture"], 0, "not-json", ""
                    )
                result.update(
                    predicate_id=fields["predicate_id"],
                    passed=fields["predicate_id"] != failed_predicate,
                )
                digests = {
                    "collection-bytes": "a" * 64,
                    "archive-member": "b" * 64,
                    "archive-chunks": "b" * 64,
                    "benign-payload": "d" * 64,
                }
                if fields["predicate_id"] in digests:
                    result["measurements"] = {
                        "passed": result["passed"],
                        "content_sha256": digests[fields["predicate_id"]],
                    }
                    if fields["predicate_id"] == "collection-bytes":
                        collection_checks.append(True)
                        if altered_collection and len(collection_checks) > 1:
                            result["measurements"]["content_sha256"] = "f" * 64
                    if fields["predicate_id"] in {"archive-member", "archive-chunks"}:
                        result["measurements"]["input_sha256"] = (
                            "a" * 64
                            if fields["predicate_id"] == "archive-member"
                            else "b" * 64
                        )
                if fields["predicate_id"] == "files-resolution":
                    import hashlib

                    result["measurements"] = dict(
                        hosts_mapping=True,
                        passed=True,
                        positive_returncode=0,
                        positive_stdout="127.0.0.1 c2.dynamic.local\n",
                        positive_stderr="",
                        negative_returncode=2,
                        negative_stdout="",
                        negative_stderr="",
                        negative_name="absent-"
                        + hashlib.sha256(fields["nonce"].encode()).hexdigest()[:20]
                        + ".invalid",
                    )
            return subprocess.CompletedProcess(
                ["guest-fixture"], 0, json.dumps(result), ""
            )
        commands.append(bash_script)
        output = (
            "/tmp/sticks_chunk.aa\n"
            if "split -b" in bash_script
            else "guest command completed\n"
        )
        return subprocess.CompletedProcess(["guest-fixture"], 0, output, "")

    monkeypatch.setattr(
        campaign_runner, "detect_lab_infrastructure", lambda profile: "qemu"
    )
    for module in (
        executor_registry,
        legacy_parity_expansion_executors,
        lab_runtime_bootstrap,
        lab_bootstrap_observer,
        c0026_capability_observers,
    ):
        monkeypatch.setattr(module, "run_bash_on_target_vm", transport)
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path / "simulation")
    return commands


def test_public_run_uses_typed_cycle_and_persists_all_six_outcomes(
    monkeypatch, tmp_path
):
    guest_fixture(monkeypatch, tmp_path)
    runner = campaign_runner.UnifiedCampaignRunner(
        "0.c0026", tmp_path / "output", require_lab=True
    )
    result = runner.run()
    assert result.schema_version == "runtime-campaign/v2"
    assert result.total_techniques == 6
    assert result.effects_observed == 5
    assert result.simulated == 1
    assert result.failed == 0
    summary = json.loads((runner.evidence_dir / "summary.json").read_text())
    assert len(summary["steps"]) == 6
    assert summary["schema_version"] == "runtime-campaign/v2"
    assert (runner.evidence_dir / "runtime_journal").is_dir()
    produced = result.steps[3].outcome.authorizing_facts[0]
    assert produced.producer_occurrence == 4
    assert produced.content_sha256 == "a" * 64
    assert produced.observation in result.steps[4].outcome.consumed_references
    assert result.steps[4].revalidation_references
    from runners.capability_authority import verify_registered_observation

    fresh_reference = result.steps[4].revalidation_references[0]
    fresh = verify_registered_observation(
        fresh_reference,
        run_root=runner.evidence_dir,
        expected_scope=produced.scope,
        expected_predicate=fresh_reference.predicate_id,
    )
    assert fresh.consumer_occurrence == 5
    assert fresh.revalidated_reference == produced.observation


def test_failed_collection_keeps_denominator_and_blocks_dependent_steps(
    monkeypatch, tmp_path
):
    guest_fixture(monkeypatch, tmp_path, failed_predicate="collection-bytes")
    runner = campaign_runner.UnifiedCampaignRunner(
        "0.c0026", tmp_path / "output", require_lab=True
    )
    result = runner.run()
    assert result.total_techniques == 6
    assert [step.status for step in result.steps] == [
        "simulated",
        "observed",
        "observed",
        "failed",
        "blocked",
        "blocked",
    ]
    assert result.failed == 3
    assert result.effects_observed == 2


def test_malformed_observer_is_error_not_unmet_precondition(monkeypatch, tmp_path):
    guest_fixture(monkeypatch, tmp_path, failed_predicate="malformed_collection")
    runner = campaign_runner.UnifiedCampaignRunner(
        "0.c0026", tmp_path / "output", require_lab=True
    )
    result = runner.run()
    assert result.steps[3].status == "error"
    assert result.steps[3].error_type == "JSONDecodeError"
    assert result.steps[3].process_failure.stdout == "not-json"
    assert result.steps[3].process_failure.returncode == 0
    records = [
        json.loads(path.read_text())
        for path in (runner.evidence_dir / "runtime_journal").glob("*.json")
    ]
    retained = next(
        record
        for record in records
        if record["phase"] == "error" and record["contract"]["occurrence"] == 4
    )
    assert retained["process_failure"]["stdout"] == "not-json"
    assert result.steps[4].status == "blocked"


def test_oversized_observer_preserves_bounded_failure_checkpoint(monkeypatch, tmp_path):
    guest_fixture(monkeypatch, tmp_path)
    original = c0026_capability_observers.run_bash_on_target_vm

    def oversized(*args, **kwargs):
        result = original(*args, **kwargs)
        if '"collection-bytes"' in result.stdout:
            result.stdout = "X" * 1_100_000
            result.stderr = "ORIGINAL_STDERR"
        return result

    monkeypatch.setattr(c0026_capability_observers, "run_bash_on_target_vm", oversized)
    runner = campaign_runner.UnifiedCampaignRunner(
        "0.c0026", tmp_path / "output", require_lab=True
    )
    report = runner.run()
    assert report.steps[3].error_type == "ValueError"
    retained = report.steps[3].process_failure
    assert retained.stderr == "ORIGINAL_STDERR"
    assert retained.stdout_truncated is True
    assert retained.stdout_bytes == 1_100_000
    assert retained.stdout_sha256 == hashlib.sha256(b"X" * 1_100_000).hexdigest()
    assert len(retained.stdout.encode()) <= 8192
    records = [
        json.loads(path.read_text())
        for path in (runner.evidence_dir / "runtime_journal").glob("*.json")
    ]
    assert any(
        record["phase"] == "error" and record["contract"]["occurrence"] == 4
        for record in records
    )


def test_public_cli_returns_zero_for_accepted_typed_fixture(monkeypatch, tmp_path):
    guest_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_campaign.py",
            "--campaign",
            "0.c0026",
            "--require-lab",
            "--output",
            str(tmp_path / "output"),
        ],
    )
    assert campaign_runner.main() == 0
    summaries = list((tmp_path / "output").glob("runtime-v2/*/summary.json"))
    assert len(summaries) == 1
    assert json.loads(summaries[0].read_text())["effects_observed"] == 5


def test_changed_collection_is_refused_before_archive_execution(monkeypatch, tmp_path):
    commands = guest_fixture(monkeypatch, tmp_path, altered_collection=True)
    runner = campaign_runner.UnifiedCampaignRunner(
        "0.c0026", tmp_path / "output", require_lab=True
    )
    result = runner.run()
    assert result.steps[4].status == "blocked"
    assert not any("tar -czf" in command for command in commands)
    assert result.failed >= 2
    assert result.steps[4].revalidation_references
