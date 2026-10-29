import subprocess
from pathlib import Path

import pytest


PROVISIONER = Path(__file__).resolve().parents[1] / "lab" / "vagrant" / "shared" / "caldera.sh"


def test_caldera_clone_is_pinned_without_a_default_branch_fallback() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")

    assert 'git clone --depth 1 --branch "$CALDERA_VERSION"' in source
    assert 'git clone --depth 1 \\' not in source
    assert "git submodule update --init --recursive" in source
    assert "plugins/manx" in source
    assert "plugins/magma" in source


def test_caldera_source_acquisition_has_bounded_waits() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")

    assert 'timeout 600 git clone --depth 1 --branch "$CALDERA_VERSION"' in source
    assert 'timeout 600 git submodule update --init --recursive --depth 1' in source
    assert source.count("wait_for_dns github.com 30 5") == 3


def test_dns_wait_recovers_from_transient_guest_lookup_failure() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")
    start = source.index("wait_for_dns() {")
    end = source.index("\n}\n", start) + 3
    function = source[start:end]
    result = subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail\n"
            "dns_attempts=0\n"
            "getent() { dns_attempts=$((dns_attempts + 1)); ((dns_attempts >= 3)); }\n"
            "sleep() { :; }\n"
            f"{function}\n"
            "wait_for_dns github.com 3 0\n"
            'printf "%s" "$dns_attempts"',
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout == "3"


def test_dns_wait_fails_when_guest_lookup_never_recovers() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")
    start = source.index("wait_for_dns() {")
    end = source.index("\n}\n", start) + 3
    function = source[start:end]
    result = subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail\n"
            "getent() { return 2; }\n"
            "sleep() { :; }\n"
            f"{function}\n"
            "wait_for_dns github.com 2 0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "DNS did not resolve github.com after 2 attempts" in result.stderr


def test_caldera_frontend_and_runtime_are_verified_before_service_start() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")

    assert "golang-1.22-go" in source
    assert "npm ci --no-audit --no-fund" in source
    assert "npm run build" in source
    assert "plugins/magma/dist/assets" in source
    assert "shasum -a 256 -c -" in source or "sha256sum -c -" in source
    assert "pip3 install --retries 5 --timeout 60" in source


def test_caldera_frontend_install_has_bounded_registry_retry() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")

    assert "timeout 900 npm ci --no-audit --no-fund" in source
    assert "--fetch-retries=5" in source
    assert "--fetch-retry-mintimeout=10000" in source
    assert "--fetch-retry-maxtimeout=60000" in source
    assert "--fetch-timeout=120000" in source
    assert source.index("npm ci --no-audit --no-fund") < source.index("npm run build")


def test_caldera_vagrantfile_accepts_an_optional_verified_node_archive() -> None:
    vagrantfile = (PROVISIONER.parents[1] / "caldera" / "Vagrantfile").read_text(
        encoding="utf-8"
    )

    assert 'ENV["STICKS_NODE_ARCHIVE"]' in vagrantfile
    assert "sticks-node-v22.22.3-linux.tar.xz" in vagrantfile


def test_caldera_service_uses_local_configuration_and_http_readiness() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")

    assert "server.py -E local --plugins" in source
    assert "server.py --insecure" not in source
    assert "curl -fsS" in source
    assert "systemctl is-active" in source
    assert "seq 1 60" in source
    assert "continuing with the remaining health checks" not in source
    assert "except Exception" not in source


def test_atomic_inputs_are_pinned_and_prepared_before_service_start() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")

    assert 'ATOMIC_COMMIT="388942adbd9641f4dfdcf079d7efe9a75ec0ac43"' in source
    assert 'timeout 600 git' in source
    assert 'fetch --depth 1 origin "$ATOMIC_COMMIT"' in source
    assert 'rev-parse HEAD)" != "$ATOMIC_COMMIT"' in source
    assert 'test -f "$atomic_dir/atomic_red_team/enterprise-attack.json"' in source
    assert source.index("\n    install_atomic_inputs\n") < source.index("\nsystemctl restart caldera\n")


def test_atomic_plugin_is_explicit_opt_in_for_cold_lab_runs() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")
    vagrantfile = (PROVISIONER.parents[1] / "caldera" / "Vagrantfile").read_text(
        encoding="utf-8"
    )

    assert 'STICKS_CALDERA_WITH_ATOMIC="${STICKS_CALDERA_WITH_ATOMIC:-0}"' in source
    assert 'if [[ "$STICKS_CALDERA_WITH_ATOMIC" == "1" ]]; then\n    install_atomic_inputs' in source
    assert 'if [[ "$STICKS_CALDERA_WITH_ATOMIC" == "1" ]]; then\n        submodules+=(plugins/atomic)' in source
    assert 'ENV.fetch("STICKS_CALDERA_WITH_ATOMIC", "0")' in vagrantfile
    assert '0) CALDERA_PLUGINS="sandcat,stockpile,response,gameboard,training,access,manx,magma"' in source


@pytest.mark.parametrize("matching_commit,with_stix,expected_exit", [(True, True, 0), (False, True, 1), (True, False, 1)])
def test_atomic_input_guard_checks_existing_checkout(
    tmp_path: Path, matching_commit: bool, with_stix: bool, expected_exit: int
) -> None:
    caldera_directory = tmp_path / "caldera"
    atomic_directory = caldera_directory / "plugins/atomic/data/atomic-red-team"
    atomic_directory.mkdir(parents=True)
    subprocess.run(["git", "init", str(atomic_directory)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(atomic_directory), "-c", "user.name=Test", "-c",
         "user.email=test@example.test", "commit", "--allow-empty", "-m", "fixture"],
        check=True, capture_output=True,
    )
    commit = subprocess.check_output(
        ["git", "-C", str(atomic_directory), "rev-parse", "HEAD"], text=True
    ).strip()
    (atomic_directory / "atomics").mkdir()
    if with_stix:
        (atomic_directory / "atomic_red_team").mkdir()
        (atomic_directory / "atomic_red_team/enterprise-attack.json").write_text("{}")
    source = PROVISIONER.read_text(encoding="utf-8")
    start = source.index("install_atomic_inputs() {")
    end = source.index("\n}\n", start) + 3
    function = source[start:end]
    expected_commit = commit if matching_commit else "0" * 40
    result = subprocess.run(
        ["bash", "-c", 'set -euo pipefail\nCALDERA_DIR="$1"\nATOMIC_COMMIT="$2"\n'
         + function + "\ninstall_atomic_inputs", "atomic-guard",
         str(caldera_directory), expected_commit],
        capture_output=True, text=True, check=False,
    )

    assert result.returncode == expected_exit
    if not matching_commit:
        assert "differ from the pinned commit" in result.stderr
