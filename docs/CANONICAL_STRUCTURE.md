# Canonical Structure (STICKS Artifact / Paper 2 Track)

This file defines the single source of truth paths to reduce pipeline confusion.

## Canonical Execution Flow

1. Reviewer-facing smoke path:
   - `artifact/setup.sh`
   - `artifact/run.sh`
   - `artifact/validate.sh`
2. Direct host-only execution:
   - `python3 scripts/run_campaign.py --campaign <id>`
3. Evidence and paper-ready refresh:
   - `./scripts/collect_evidence.sh`
4. Canonical VM-backed realism execution:
   - `python3 scripts/run_lab_campaign.py --campaign <id> [--provider ...]`
5. Low-level lab helpers used by the realism path:
   - `./scripts/up_lab.sh --campaign <id> [--provider ...]`
   - `./scripts/destroy_lab.sh --campaign <id>`

## Canonical Data Paths

- Published campaign corpus:
  - `campaigns/*.json`
- Internal YAML campaign definitions:
  - `data/campaigns/*.yml`
- SUT profiles:
  - `data/sut_profiles/*.yml`
- Loader and validation logic:
  - `src/loaders/`
- Evidence output:
  - `release/evidence/<campaign_timestamp>/`
- Paper-facing mirrors:
  - `results/`
  - `results/values.tex` = executable published-subset macros
  - `measurement/sut/scripts/results/todo_values_latex.tex` = Paper 2 measurement macros
  - `../ACM CCS - Paper 2/results/values.tex` = Paper 2 tracked manuscript macro surface
  - `scripts/sync_manuscript_values.py` = syncs Paper 2 canonical generated macros into the manuscript
  - Paper 1 measurement lives outside this tree in `../sticks-docker/measurement/scripts/analyze_campaigns.py`
  - Paper 1 manuscript sync lives in `../sticks-docker/measurement/scripts/sync_paper1_values.py`
- Reviewer-facing documentation aliases:
  - `docs/reviewer_quickstart.md`

## Legacy / Secondary Paths (Do Not Use for New Work)

These remain temporarily for backward compatibility or historical traceability:

- `artifact/artifact_up.sh`
- `campaign_pipeline.py`
- `evidence_collector.py`
- `paper_generator.py`
- `measurement/sut/scripts/*` for Paper 2 measurement workflows only

## Naming and Scope

- `campaigns/` = published JSON corpus used in the papers
- `data/` = internal YAML campaign/SUT definitions
- `src/` = canonical loader, runner, and executor code
- `lab/` = VM-backed infrastructure and SUT provisioning
- `measurement/` = analysis and Paper 2 measurement workflows

For artifact evaluation, use the canonical flow above. Treat the host-only
smoke path as the baseline contract and `scripts/run_lab_campaign.py` as the
canonical realism path when VM-backed evidence is needed.

For manuscript maintenance, keep each paper-local `results/` directory as a
minimal consumption boundary. In practice, that means `results/values.tex`
should be the only generated file mirrored inside the paper tree. Richer
analysis outputs belong under `sticks/results/` or `sticks/release/`, where
they can be regenerated, audited, and versioned without cluttering the
manuscript directories.

## Sanitization Policy (Progressive)

1. Keep one reviewer-facing path per responsibility.
2. Mirror generated reviewer artifacts into `release/` and `results/`.
3. Keep exploratory or legacy scripts out of the canonical mental path.
4. Remove empty compatibility directories and typo paths before packaging.
5. Treat `.vagrant/`, `__pycache__/`, and `.pytest_cache/` as local runtime
   residue, never as reviewer-facing state.
