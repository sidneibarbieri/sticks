# Campaign-SUT-Fidelity Matrix

Source of truth:
- Published campaigns with a matching SUT profile only
- Exact `<campaign_id>_YYYYMMDD_HHMMSS` evidence directory matching per campaign
- `release/evidence/*/summary.json` (latest exact match per campaign)
- `release/fidelity_report.json` (rubric consistency when available)
- `src/loaders/campaign_loader.py` (`validate_campaign_sut_pair`)
- Rows without shipped evidence are shown explicitly rather than treated as failed runs

| Campaign | SUT Profile | Pair Valid | Evidence | Latest Evidence Dir | Total | Success | Failed | Skipped | Faithful | Adapted | Inspired | Rubric Total | Rubric Consistent | Rubric Mismatches |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `0.apt41_dust` | `0.apt41_dust` | yes | no | `-` | -- | -- | -- | -- | -- | -- | -- | 13 | 3 | 10 |
| `0.apt41_dust_full` | `0.apt41_dust_full` | no | no | `-` | -- | -- | -- | -- | -- | -- | -- | 10 | 2 | 8 |
| `0.c0010` | `0.c0010` | yes | no | `-` | -- | -- | -- | -- | -- | -- | -- | 9 | 4 | 5 |
| `0.c0011` | `0.c0011` | yes | yes | `0.c0011_20260407_164253` | 11 | 11 | 0 | 0 | 0 | 4 | 7 | 11 | 9 | 2 |
| `0.c0012` | `0.c0012` | yes | no | `-` | -- | -- | -- | -- | -- | -- | -- | 3 | 2 | 1 |
| `0.c0013` | `0.c0013` | no | no | `-` | -- | -- | -- | -- | -- | -- | -- | 4 | 3 | 1 |
| `0.c0015` | `0.c0015` | yes | no | `-` | -- | -- | -- | -- | -- | -- | -- | 5 | 2 | 3 |
| `0.c0017` | `0.c0017` | yes | no | `-` | -- | -- | -- | -- | -- | -- | -- | 6 | 2 | 4 |
| `0.c0026` | `0.c0026` | yes | no | `-` | -- | -- | -- | -- | -- | -- | -- | 6 | 6 | 0 |
| `0.costaricto` | `0.costaricto` | yes | no | `-` | -- | -- | -- | -- | -- | -- | -- | 10 | 8 | 2 |
| `0.operation_midnighteclipse` | `0.operation_midnighteclipse` | yes | no | `-` | -- | -- | -- | -- | -- | -- | -- | 18 | 4 | 14 |
| `0.outer_space` | `0.outer_space` | yes | no | `-` | -- | -- | -- | -- | -- | -- | -- | 8 | 6 | 2 |
| `0.salesforce_data_exfiltration` | `0.salesforce_data_exfiltration` | yes | no | `-` | -- | -- | -- | -- | -- | -- | -- | 12 | 3 | 9 |
| `0.shadowray` | `0.shadowray` | yes | yes | `0.shadowray_20260407_173127` | 10 | 10 | 0 | 0 | 0 | 9 | 1 | 10 | 4 | 6 |

## Pair Validation Exceptions

- `0.apt41_dust_full`: Fidelity mismatch for T1490: campaign expects adapted, SUT expects inspired
- `0.c0013`: Fidelity mismatch for T1055: campaign expects adapted, SUT expects inspired
