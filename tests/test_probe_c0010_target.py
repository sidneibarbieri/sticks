"""Bounded C0010 target-observation regression cases."""

from pathlib import Path

import pytest

from scripts.probe_c0010_target import (
    EXPECTED_NOTICE,
    EXPECTED_PAGE,
    EXPECTED_PAYLOAD,
    collect_observation,
)
from scripts import probe_c0010_target


def write_fixture(root: Path, relative: str, content: bytes) -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def make_target(root: Path) -> None:
    write_fixture(root, "home/ubuntu/shipping_notice.txt", EXPECTED_NOTICE)
    write_fixture(root, "var/www/html/index.html", EXPECTED_PAGE)
    write_fixture(root, "tmp/sticks_t1105/payload.sh", EXPECTED_PAYLOAD)
    downloaded = write_fixture(
        root, "tmp/sticks_downloaded_payload.sh", EXPECTED_PAYLOAD
    )
    downloaded.chmod(0o755)
    write_fixture(
        root, "tmp/sticks_t1105_server.log", b'"GET /payload.sh HTTP/1.1" 200 -\n'
    )
    write_fixture(root, "proc/sys/kernel/random/boot_id", b"test-boot-id\n")


def test_c0010_probe_accepts_target_fixture_and_transfer(tmp_path: Path) -> None:
    make_target(tmp_path)

    observation = collect_observation(tmp_path)

    assert observation["passed"]
    assert all(observation["checks"].values())


def test_readiness_requires_only_profile_fixtures_before_transfer(tmp_path):
    write_fixture(tmp_path, 'home/ubuntu/shipping_notice.txt', EXPECTED_NOTICE)
    write_fixture(tmp_path, 'var/www/html/index.html', EXPECTED_PAGE)
    result = probe_c0010_target.collect_fixture_readiness(tmp_path)
    assert result == {'notice_matches': True, 'page_matches': True}


def test_readiness_does_not_hide_missing_profile(tmp_path):
    with pytest.raises(FileNotFoundError):
        probe_c0010_target.collect_fixture_readiness(tmp_path)


def test_readiness_reports_changed_notice(tmp_path):
    write_fixture(tmp_path, 'home/ubuntu/shipping_notice.txt', b'changed')
    write_fixture(tmp_path, 'var/www/html/index.html', EXPECTED_PAGE)
    result = probe_c0010_target.collect_fixture_readiness(tmp_path)
    assert result == {'notice_matches': False, 'page_matches': True}


def test_c0010_probe_rejects_drifted_download(tmp_path: Path) -> None:
    make_target(tmp_path)
    (tmp_path / "tmp/sticks_downloaded_payload.sh").write_bytes(b"changed")

    observation = collect_observation(tmp_path)

    assert not observation["passed"]
    assert not observation["checks"]["transfer_matches_source"]


def test_c0010_probe_rejects_missing_http_get(tmp_path: Path) -> None:
    make_target(tmp_path)
    (tmp_path / "tmp/sticks_t1105_server.log").write_bytes(b"empty\n")

    observation = collect_observation(tmp_path)

    assert not observation["passed"]
    assert not observation["checks"]["http_get_recorded"]


def test_c0010_probe_rejects_symlinked_download(tmp_path: Path) -> None:
    make_target(tmp_path)
    downloaded = tmp_path / "tmp/sticks_downloaded_payload.sh"
    downloaded.unlink()
    downloaded.symlink_to(tmp_path / "tmp/sticks_t1105/payload.sh")

    with pytest.raises(OSError):
        collect_observation(tmp_path)


def test_c0010_probe_rejects_symlinked_fixture_directory(tmp_path: Path) -> None:
    make_target(tmp_path)
    fixture_directory = tmp_path / "tmp/sticks_t1105"
    moved_directory = tmp_path / "tmp/sticks_t1105_original"
    fixture_directory.rename(moved_directory)
    fixture_directory.symlink_to(moved_directory, target_is_directory=True)

    with pytest.raises(OSError):
        collect_observation(tmp_path)
