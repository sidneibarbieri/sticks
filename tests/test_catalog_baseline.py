from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))
from evaluation.technique_coverage import coverage_extension, indexed_step_count


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sibling_subtechniques_are_not_interchangeable():
    counts = Counter({'T1059.001': 2, 'T1059.004': 1, 'T1059': 4})
    assert indexed_step_count(counts, {'T1059.004'}) == 1
    assert indexed_step_count(counts, {'T1059'}) == 4


def test_catalog_union_does_not_double_count_shared_techniques():
    counts = Counter({'T1105': 3, 'T1059.001': 2, 'T1059.004': 1})
    report = coverage_extension(counts, {'T1105'}, {'T1105', 'T1059.004'})
    assert report['extended_contract_reach_steps'] == 4
    assert report['incremental_draft_reach_steps'] == 1
    assert report['admitted_step_reach'] == 4
    assert coverage_extension({}, set(), set())['extended_contract_reach_share'] == 0


def test_released_comparison_recomputes_from_exact_inputs():
    script = load_script('build_catalog_baseline_evidence')
    counts, campaigns = script.corpus_step_techniques()
    report = json.loads(script.OUTPUT.read_text())
    templates = json.loads(script.CATALOG.read_text())['templates']
    trusted = {technique for template in templates for technique in template['technique_ids']}
    external = set(script.BASELINE.read_text().split())
    assert report['total_campaigns'] == campaigns
    assert report['our_reach_steps'] == indexed_step_count(counts, trusted)
    assert report['baseline_reach_steps'] == indexed_step_count(counts, external)
    assert report['union_uncovered_steps'] == sum(counts.values()) - indexed_step_count(counts, trusted | external)


def test_author_targets_include_unsupported_siblings(tmp_path, monkeypatch):
    script = load_script('author_catalog_templates')
    catalog = tmp_path / 'catalog.json'
    catalog.write_text(json.dumps({'templates': [{'technique_ids': ['T1059.004']}]}))
    (tmp_path / 'example.procedural-plan.json').write_text(json.dumps({
        'steps': [{'technique_id': 'T1059.004'}, {'technique_id': 'T1059.001'}]
    }))
    monkeypatch.setattr(script, 'CATALOG', catalog)
    monkeypatch.setattr(script, 'PLANS', tmp_path)
    assert script.uncovered_by_coverage() == [('T1059.001', 1)]


def test_author_explicit_targets_do_not_expand_a_provider_batch():
    script = load_script('author_catalog_templates')
    uncovered = [('T1001', 8), ('T1002', 5), ('T1003', 2)]
    assert script.select_targets(uncovered, ['T1003', 'T1001'], 40) == [
        ('T1003', 2),
        ('T1001', 8),
    ]


def test_author_explicit_targets_reject_covered_or_unknown_techniques():
    import pytest

    script = load_script('author_catalog_templates')
    with pytest.raises(ValueError, match='already covered or absent'):
        script.select_targets([('T1001', 8)], ['T1002'], 1)


def test_author_refuses_to_delete_preserved_evidence(tmp_path, monkeypatch):
    import pytest
    script = load_script('author_catalog_templates')
    call_dir = tmp_path / 'T1105'
    call_dir.mkdir()
    evidence = call_dir / 'provider_response.json'
    evidence.write_text('preserved')
    vocabulary = type('Vocabulary', (), {'predicate_roles': {}, 'effect_predicates': set()})()
    with pytest.raises(FileExistsError):
        script.author_one('T1105', call_dir, {}, None, None, vocabulary, set())
    assert evidence.read_text() == 'preserved'
