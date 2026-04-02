# Script Analysis - Classification

## Current Scripts (23 total)

### Official (Working)
- `run_campaign.py` - Main execution script, validated

### Auxiliary
- `generate_sut_specs.py` - SUT generation
- `render_figures.py` - Figure generation
- `orchestrator.py` - Orchestration

### Legacy (Not in Official Path)
- `campaign_runner.py`
- `automated_campaign_runner.py`
- `real_campaign_runner.py`
- `execute_campaign.py`
- `run_campaign_batch.py`
- `run_full_pipeline.py`

### Analysis Only
- `analyze_group_specificity.py`
- `campaign_analyzer.py`
- `compare_related_work.py`
- `generate_case_studies.py`
- `generate_paper1_additions.py`
- `generate_traceability.py`

### Other
- `agent_deployer.py`
- `filter_linux_executors.py`
- `llm_environment_inference.py`
- `evaluate_compatibility_validation.py`
- `sut_provisioner.py`
- `sut_measurement_pipeline.py`
- `sanitize_bibliography_policy.py`

## Action

Keep only:
- `run_campaign.py` (official)
- `generate_sut_specs.py` (if needed)
- `render_figures.py` (if needed)

Move others to archive/ or remove.
