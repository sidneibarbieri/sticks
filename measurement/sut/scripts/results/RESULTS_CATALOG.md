# Results Catalog - Measurement Layer

## Current Results Structure

```
results/
├── executions/           # Live execution results
├── audit/              # Audit results
├── sut_specs/          # SUT specifications
├── paper1_additions/    # Paper 1 specific
├── sandbox/            # Testing area
├── *.json              # Individual results
└── *.tex               # LaTeX outputs
```

## Classification

| Category | Type | Status |
|----------|------|--------|
| executions/*.json | Real execution | OBSERVED |
| audit/* | Offline analysis | DERIVED |
| sut_specs/* | Offline analysis | DERIVED |
| *.json (root) | Mixed | NEEDS REVIEW |

## Key Results

| File | Type | Evidence | Valid |
|------|------|----------|-------|
| 0.solarwinds_compromise_results.json | Real execution | OBSERVED | ✅ |
| 0.apt28_nearest_neighbor_campaign_results.json | Real execution | OBSERVED | ✅ |
| figures_data.json | Derived | OFFLINE | ✅ |
| compatibility_validation_summary.json | Derived | OFFLINE | ✅ |

## Issues Identified

1. Results mixed in root folder
2. Sandbox folder not cleaned
3. Some results may be deprecated

## Action Items

1. Separate observed vs derived
2. Clean sandbox
3. Add classification tags
