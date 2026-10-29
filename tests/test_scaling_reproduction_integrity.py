"""Timing diagnostics must not invalidate the preserved public evidence."""

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_repeated_scaling_preserves_public_tree(tmp_path, monkeypatch):
    scaling = load_script("build_enumeration_scaling_evidence")
    manifest = load_script("public_tree_manifest")
    evidence = tmp_path / "release/experiments/enumeration_scaling/corpus.json"
    timing = tmp_path / "results/enumeration_scaling_timing.json"
    monkeypatch.setattr(scaling, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scaling, "OUTPUT", evidence)
    monkeypatch.setattr(scaling, "TIMING", timing)
    monkeypatch.setattr(scaling, "TEMPLATES_PER_TECHNIQUE", (1,))
    monkeypatch.setattr(scaling, "PARAMETERS_PER_TEMPLATE", (1,))
    monkeypatch.setattr(scaling, "BINDINGS_PER_KIND", (1,))

    scaling.main()
    historical_timing = evidence.with_name("timing.json")
    historical_timing.write_text('{"historical": true}\n', encoding="utf-8")
    manifest_path = tmp_path / manifest.DEFAULT_MANIFEST_NAME
    manifest.write_manifest(tmp_path, manifest_path)
    original_evidence = evidence.read_bytes()

    scaling.main()
    assert evidence.read_bytes() == original_evidence
    assert historical_timing.read_text() == '{"historical": true}\n'
    assert timing.is_file()
    manifest.verify_manifest(tmp_path, manifest_path)

    timing.write_text('{"frozen": true}\n', encoding="utf-8")
    scaling.main(write_timing=False)
    assert timing.read_text(encoding="utf-8") == '{"frozen": true}\n'
    manifest.verify_manifest(tmp_path, manifest_path)

    evidence.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="public tree integrity failure"):
        manifest.verify_manifest(tmp_path, manifest_path)
