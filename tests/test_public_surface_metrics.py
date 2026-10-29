from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "check_public_surface.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_public_surface_metrics", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_readme_headline_values_match_generated_paper_macros() -> None:
    module = _load_module()
    assert module.find_readme_metric_mismatches() == []


def test_public_surface_audit_runs_without_git_binary(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module.shutil, "which", lambda name: None)

    assert not module.is_git_ignored("README.md")


def test_generic_container_home_is_not_personal() -> None:
    module = _load_module()

    assert module.home_path_snippets(Path("/root")) == []
    assert module.home_path_snippets(Path("/Users/example")) == ["/Users/example"]


def test_administrative_terms_are_matched_by_digest_as_tokens_and_phrases(monkeypatch) -> None:
    module = _load_module()
    digests = frozenset({module.term_digest("Zebra-Venue"), module.term_digest("Quiet Forum")})
    monkeypatch.setattr(module, "ADMINISTRATIVE_TERM_DIGESTS", digests)

    assert module.contains_administrative_term("Accepted at Zebra-Venue.")
    assert module.contains_administrative_term("presented at the Quiet Forum in May")
    assert not module.contains_administrative_term("a Zebra venue and a quiet forum")


def test_administrative_term_digests_are_hex_and_never_plain_text() -> None:
    module = _load_module()
    assert module.ADMINISTRATIVE_TERM_DIGESTS
    assert all(len(digest) == 16 and int(digest, 16) >= 0 for digest in module.ADMINISTRATIVE_TERM_DIGESTS)


def test_check_only_keeps_frozen_reports_unchanged(tmp_path, monkeypatch) -> None:
    module = _load_module()
    report_json = tmp_path / "public_surface_report.json"
    report_markdown = tmp_path / "PUBLIC_SURFACE_REPORT.md"
    report_json.write_text("frozen\n", encoding="utf-8")
    report_markdown.write_text("frozen\n", encoding="utf-8")
    monkeypatch.setattr(module, "OUTPUT_JSON", report_json)
    monkeypatch.setattr(module, "OUTPUT_MD", report_markdown)
    monkeypatch.setattr(module, "build_report", lambda: {"status": "clean"})

    module.main(write_reports=False)

    assert report_json.read_text(encoding="utf-8") == "frozen\n"
    assert report_markdown.read_text(encoding="utf-8") == "frozen\n"

    monkeypatch.setattr(module, "build_report", lambda: {"status": "needs_attention"})
    with pytest.raises(SystemExit) as failure:
        module.main(write_reports=False)
    assert failure.value.code == 1
    assert report_json.read_text(encoding="utf-8") == "frozen\n"


def test_public_surface_rejects_embedded_legacy_caldera_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    runner = tmp_path / "measurement/sut/scripts/run_campaign.py"
    runner.parent.mkdir(parents=True)
    runner.write_text('PASSWORD = "synthetic-lab-secret"\n', encoding="utf-8")
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(module, "is_git_ignored", lambda relative_path: False)

    assert module.find_sensitive_text_hits() == [
        {
            "path": "measurement/sut/scripts/run_campaign.py",
            "snippet": "embedded legacy Caldera password",
        }
    ]


def test_public_surface_rejects_lab_profile_key_header_without_valid_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    profile = tmp_path / "lab/sut_profiles/example.yml"
    profile.parent.mkdir(parents=True)
    private_key_header = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
    profile.write_text(
        f"content: |\n  {private_key_header}\n  placeholder...\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(module, "is_git_ignored", lambda relative_path: False)

    assert module.find_sensitive_text_hits() == [
        {"path": "lab/sut_profiles/example.yml", "snippet": "lab profile private key"}
    ]
