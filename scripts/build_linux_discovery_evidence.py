#!/usr/bin/env python3
"""Recompute the extension summary from two preserved isolated executions."""
import json
from pathlib import Path

from qualify_linux_discovery import measure_reach
from verify_linux_discovery import verify

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'release/experiments/linux_discovery'


def main() -> None:
    bundles = [RUNS / 'run-20260919-final', RUNS / 'run-20260919-final-repeat']
    qualified_sets = [set(verify(bundle)) for bundle in bundles]
    if qualified_sets[0] != qualified_sets[1]:
        raise ValueError('Qualified technique sets differ between runs')
    qualified = qualified_sets[0]
    reach = measure_reach(qualified)
    report = {'repetitions': len(bundles), 'qualified_techniques': sorted(qualified),
              'qualified_technique_count': len(qualified),
              'procedure_executions': sum(len(items) for items in qualified_sets),
              **reach,
              'claim_boundary': 'Isolated Linux discovery with granted shell access; no campaign-wide execution claim'}
    (RUNS / 'corpus.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    macros = {
        'discoveryTechniques': report['qualified_technique_count'],
        'discoveryRepeats': report['repetitions'],
        'discoveryExecutions': report['procedure_executions'],
        'discoveryAddedSteps': report['extension_index_reach'],
        'discoveryUnionSteps': report['union_index_reach'],
        'discoveryBaselineSteps': report['baseline_index_reach'],
        'discoveryCorpusSteps': report['corpus_steps'],
    }
    (ROOT / 'release/linux_discovery_macros.tex').write_text(
        '% Generated from preserved discovery qualification evidence.\n' +
        ''.join('\\newcommand{\\' + name + '}{' + str(value) + '}\n'
                for name, value in macros.items()))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
