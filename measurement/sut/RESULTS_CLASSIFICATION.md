# Results Classification

## Analysis of 12 Result Files

The files in `results/executions/*_full_results.json` show:
- success: true
- linux_coverage: 100.0%
- platform: linux

However, the schema differs from current `run_campaign.py` output:
- No operation_id
- No agent details
- No links observed
- Calculated "coverage" without live execution

## Classification

| File | Type | Notes |
|------|------|-------|
| 0.3cx_supply_chain_attack | OFFLINE ANALYSIS | Coverage calculated, no live execution |
| 0.apt28_nearest_neighbor_campaign | OFFLINE ANALYSIS | Same |
| 0.apt41_dust | OFFLINE ANALYSIS | Same |
| 0.arcanedoor | OFFLINE ANALYSIS | Same |
| 0.c0010 | OFFLINE ANALYSIS | Same |
| 0.c0011 | OFFLINE ANALYSIS | Same |
| 0.c0015 | OFFLINE ANALYSIS | Same |
| 0.c0017 | OFFLINE ANALYSIS | Same |
| 0.operation_dream_job | OFFLINE ANALYSIS | Same |
| 0.operation_wocao | OFFLINE ANALYSIS | Same |
| 0.sharepoint_toolshell_exploitation | OFFLINE ANALYSIS | Same |
| 0.solarwinds_compromise | OFFLINE ANALYSIS | Same |

## Current Real Execution

The only real observed execution is:
- `results/0.solarwinds_compromise_results.json` - from run_campaign.py
- Technique T1070.003 observed
- 3 agents used

## Recommendation

These 12 files should be moved to `results/offline/` as they represent analysis, not live execution.
