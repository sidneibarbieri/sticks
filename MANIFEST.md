# Manifest

## Canonical Interface

- `run_review_check.sh`
- `run_vm_backed_campaign.sh`
- `artifact/setup.sh`
- `artifact/run.sh`
- `artifact/validate.sh`
- `artifact/teardown.sh`

## Core Execution Code

- `scripts/run_campaign.py`
- `scripts/generate_tables.py`
- `src/loaders/campaign_loader.py`
- `src/runners/campaign_runner.py`
- `src/executors/executor_registry.py`
- `src/executors/registry_initializer.py`

## Campaign and SUT Inputs

- `campaigns/`
- `data/campaigns/`
- `data/sut_profiles/`

## Evidence and Results

- `release/evidence/` (generated at run time)
- `results/tables/`
- `results/` synthesized reports and paper-facing summaries

## Optional Infrastructure Helpers

- `scripts/up_lab.sh`
- `scripts/destroy_lab.sh`
- `multi_vm_manager_2vm.py`
- `lab/`

## Publication Boundaries

- `PUBLIC_REPOSITORY_SCOPE.md` defines what should remain public and stable for
  reviewer-facing GitHub publication.
- `scripts/check_public_surface.py` audits the repository against that scope.
- Optional VM-backed infrastructure remains heavier than the fast validation
  path, but the public artifact can still expose it as an explicit second-tier
  reviewer path.

## Non-Canonical Historical Material

- exploratory reports and one-off root-level JSON/MD summaries
- root-level orchestration wrappers such as `campaign_pipeline.py`,
  `evidence_collector.py`, and `paper_generator.py`

These files may still be useful to the authors, but they are not the primary
reviewer surface.
