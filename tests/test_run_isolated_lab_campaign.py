import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_isolated_lab_campaign as isolated_run
from scripts.run_isolated_lab_campaign import copy_workspace, tree_manifest


def test_run_campaign_pathname_bootstrap_exposes_project_root(tmp_path: Path) -> None:
    """The reviewer entrypoint must resolve root-level observer modules."""
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, str(project_root / "scripts" / "run_campaign.py"), "--help"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Unified Campaign Runner" in result.stdout


def test_copy_workspace_excludes_runtime_state_and_prior_artifacts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    (source / "data" / "artifacts").mkdir(parents=True)
    (source / "lab" / "vagrant" / "caldera" / ".vagrant").mkdir(parents=True)
    (source / ".playwright-cli").mkdir()
    (source / "runs" / "previous").mkdir(parents=True)
    (source / "_private" / "prepared-images").mkdir(parents=True)
    (source / "scripts").mkdir()
    (source / "scripts" / "run_campaign.py").write_text("pass\n", encoding="utf-8")
    (source / "data" / "artifacts" / "stale.txt").write_text("stale", encoding="utf-8")
    (source / "lab" / "vagrant" / "caldera" / ".vagrant" / "id").write_text(
        "vm-id", encoding="utf-8"
    )
    (source / ".env").write_text("local-only", encoding="utf-8")
    (source / ".playwright-cli" / "page.yml").write_text("stale", encoding="utf-8")
    (source / "runs" / "previous" / "summary.json").write_text("{}", encoding="utf-8")
    (source / "_private" / "prepared-images" / "caldera.box").write_bytes(b"private")
    (source / "config.local.json").write_text("private", encoding="utf-8")
    (source / "config.author.local.json").write_text("private", encoding="utf-8")
    (source / "config.example.json").write_text("public", encoding="utf-8")

    workspace = tmp_path / "run" / "workspace"
    copy_workspace(source, workspace)

    assert (workspace / "scripts" / "run_campaign.py").is_file()
    assert not (workspace / "data" / "artifacts").exists()
    assert not (workspace / "lab" / "vagrant" / "caldera" / ".vagrant").exists()
    assert not (workspace / ".env").exists()
    assert not (workspace / ".playwright-cli").exists()
    assert not (workspace / "runs").exists()
    assert not (workspace / "_private").exists()
    assert not (workspace / "config.local.json").exists()
    assert not (workspace / "config.author.local.json").exists()
    assert (workspace / "config.example.json").is_file()


def test_copy_workspace_preserves_published_run_evidence(tmp_path: Path) -> None:
    source = tmp_path / "source"
    evidence_path = Path(
        "release/experiments/stage2_authoring/runs/frozen/calls/001.json"
    )
    frozen_call = source / evidence_path
    frozen_call.parent.mkdir(parents=True)
    frozen_call.write_bytes(b'{"decision": "admitted"}\n')
    workspace = tmp_path / "workspace"

    copy_workspace(source, workspace)

    assert (workspace / evidence_path).read_bytes() == frozen_call.read_bytes()
    assert tree_manifest(workspace) == tree_manifest(source)


def test_copy_workspace_rejects_insufficient_space_before_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "input.json").write_bytes(b"123456")
    destination = tmp_path / "run" / "workspace"
    monkeypatch.setattr(
        isolated_run.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=5),
    )

    with pytest.raises(OSError, match="Insufficient space for workspace copy"):
        copy_workspace(source, destination)

    assert not destination.exists()


def test_vm_host_capacity_rejects_less_than_documented_minimum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        isolated_run.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(
            free=isolated_run.MINIMUM_VM_HOST_FREE_BYTES - 1
        ),
    )

    with pytest.raises(OSError, match="Insufficient free space for VM-backed execution"):
        isolated_run.require_vm_host_capacity(tmp_path)


def test_tree_manifest_changes_when_a_source_file_changes(tmp_path: Path) -> None:
    file_path = tmp_path / "run.py"
    file_path.write_text("first\n", encoding="utf-8")
    first = tree_manifest(tmp_path)

    file_path.write_text("second\n", encoding="utf-8")
    second = tree_manifest(tmp_path)

    assert first["tree_sha256"] != second["tree_sha256"]
    assert first["files"][0]["path"] == "run.py"


def test_tree_manifest_excludes_declared_runtime_outputs(tmp_path: Path) -> None:
    source_file = tmp_path / "src" / "runner.py"
    source_file.parent.mkdir()
    source_file.write_text("frozen", encoding="utf-8")
    runtime_file = tmp_path / "release" / "realistic_data" / "sample.json"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text("first", encoding="utf-8")

    first = tree_manifest(
        tmp_path,
        excluded_relative_roots=isolated_run.SOURCE_MANIFEST_SKIP_DIRS,
    )
    runtime_file.write_text("second", encoding="utf-8")
    second = tree_manifest(
        tmp_path,
        excluded_relative_roots=isolated_run.SOURCE_MANIFEST_SKIP_DIRS,
    )

    assert first == second
    assert [entry["path"] for entry in first["files"]] == ["src/runner.py"]


def test_stale_qemu_socket_fails_before_creating_a_run(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    socket_path = Path("socket_vmnet")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(socket_path))
    run_root = tmp_path / "run"
    monkeypatch.setattr(isolated_run.platform, "system", lambda: "Darwin")
    monkeypatch.setenv("STICKS_SOCKET_VMNET_SOCKET", str(socket_path))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_isolated_lab_campaign.py",
            "--campaign",
            "0.outer_space",
            "--provider",
            "qemu",
            "--run-root",
            str(run_root),
        ],
    )

    with pytest.raises(
        ConnectionError, match="start the private-network daemon"
    ) as failure:
        isolated_run.main()

    assert isinstance(failure.value.__cause__, ConnectionRefusedError)
    assert not run_root.exists()


def test_default_socket_vmnet_requires_exactly_one_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = isolated_run.SOCKET_VMNET_BINARY
    monkeypatch.setattr(
        isolated_run.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=f"101 {binary} --first\n102 {binary} --second\n"
        ),
    )

    with pytest.raises(RuntimeError, match="exactly one socket_vmnet daemon"):
        isolated_run.require_single_socket_vmnet_daemon()


def test_shadowray_generic_runner_fails_before_creating_a_run(
    tmp_path: Path, monkeypatch
) -> None:
    run_root = tmp_path / "run"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_isolated_lab_campaign.py",
            "--campaign",
            "0.shadowray",
            "--run-root",
            str(run_root),
        ],
    )

    with pytest.raises(ValueError, match="frozen effect-series runner"):
        isolated_run.main()

    assert not run_root.exists()


def test_literal_caldera_secret_fails_before_creating_a_run(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    runner_dir = source / "measurement" / "sut" / "scripts"
    runner_dir.mkdir(parents=True)
    (runner_dir / "run_campaign.py").write_text(
        'password = "synthetic-lab-secret"\n', encoding="utf-8"
    )
    (runner_dir / "run_finite.py").write_text(
        'password = os.environ["CALDERA_PASSWORD"]\n', encoding="utf-8"
    )
    run_root = tmp_path / "run"
    monkeypatch.setattr(isolated_run, "PROJECT_ROOT", source)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_isolated_lab_campaign.py",
            "--campaign",
            "0.c0010",
            "--provider",
            "libvirt",
            "--run-root",
            str(run_root),
        ],
    )

    with pytest.raises(ValueError, match="embeds a literal credential"):
        isolated_run.main()

    assert not run_root.exists()


def test_literal_caldera_api_key_fails_before_creating_a_run(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "caldera_manager.py").write_text(
        'CALDERA_API_KEY = "synthetic-test-key"\n', encoding="utf-8"
    )
    run_root = tmp_path / "run"
    monkeypatch.setattr(isolated_run, "PROJECT_ROOT", source)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_isolated_lab_campaign.py",
            "--campaign",
            "0.c0010",
            "--provider",
            "libvirt",
            "--run-root",
            str(run_root),
        ],
    )

    with pytest.raises(ValueError, match="embeds a literal credential"):
        isolated_run.main()

    assert not run_root.exists()


@pytest.mark.parametrize("exit_code", [0, 7])
def test_campaign_keeps_context_log_and_raw_artifacts(
    tmp_path: Path, monkeypatch, capfd, exit_code: int
) -> None:
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    runner_dir = source / "measurement" / "sut" / "scripts"
    runner_dir.mkdir(parents=True)
    for name in ("run_campaign.py", "run_finite.py"):
        (runner_dir / name).write_text(
            'password = os.environ["CALDERA_PASSWORD"]\n', encoding="utf-8"
        )
    (source / "scripts" / "run_lab_campaign.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "output = Path(sys.argv[sys.argv.index('--evidence-output') + 1])\n"
        "output.mkdir()\n"
        "(output / 'health.json').write_text('{}', encoding='utf-8')\n"
        "artifact = Path('data/artifacts')\n"
        "artifact.mkdir(parents=True)\n"
        "(artifact / 'raw.txt').write_text('observed', encoding='utf-8')\n"
        "print(f'output path: {output}', flush=True)\n"
        "print('stdout marker', flush=True)\n"
        "print('stderr marker', file=sys.stderr, flush=True)\n"
        f"raise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    run_root = tmp_path / "run"

    monkeypatch.setattr(isolated_run, "PROJECT_ROOT", source)
    monkeypatch.setattr(isolated_run, "require_vm_host_capacity", lambda path: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_isolated_lab_campaign.py",
            "--campaign",
            "0.c0011",
            "--provider",
            "libvirt",
            "--run-root",
            str(run_root),
            "--keep-lab",
        ],
    )

    assert isolated_run.main() == exit_code
    context = json.loads((run_root / "run_context.json").read_text(encoding="utf-8"))
    assert context["exit_code"] == exit_code
    assert context["keep_lab_requested"] is True
    assert context["artifact_tree_sha256"]
    assert context["execution_log_path"] == "execution.log"
    assert context["execution_log_sha256"] == isolated_run.sha256_file(
        run_root / "execution.log"
    )
    assert b"stdout marker" in (run_root / "execution.log").read_bytes()
    assert b"stderr marker" in (run_root / "execution.log").read_bytes()
    assert (
        b"output path: <RUN_ROOT>/evidence" in (run_root / "execution.log").read_bytes()
    )
    assert str(run_root).encode() not in (run_root / "execution.log").read_bytes()
    console_output = capfd.readouterr().out
    assert "stdout marker" in console_output
    assert "stderr marker" in console_output
    assert (run_root / "artifact_manifest.json").is_file()
    assert (run_root / "evidence_manifest.json").is_file()
