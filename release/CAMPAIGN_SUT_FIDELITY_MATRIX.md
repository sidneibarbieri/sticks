# Campaign-SUT-Fidelity Matrix

Source of truth:
- Published campaigns with a matching SUT profile only
- Exact `<campaign_id>_YYYYMMDD_HHMMSS` evidence directory matching per campaign
- `release/evidence/*/summary.json` (latest exact match per campaign)
- `release/fidelity_report.json` (rubric consistency when available)
- `src/loaders/campaign_loader.py` (`validate_campaign_sut_pair`)

| Campaign | SUT Profile | Pair Valid | Latest Evidence Dir | Total | Success | Failed | Skipped | Faithful | Adapted | Inspired | Rubric Total | Rubric Consistent | Rubric Mismatches |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `0.apt41_dust` | `0.apt41_dust` | yes | `0.apt41_dust_20260402_141429` | 23 | 23 | 0 | 0 | 0 | 16 | 7 | 13 | 3 | 10 |
| `0.apt41_dust_full` | `0.apt41_dust_full` | no | `0.apt41_dust_full_20260401_113231` | 10 | 10 | 0 | 0 | 0 | 9 | 1 | 10 | 2 | 8 |
| `0.c0010` | `0.c0010` | yes | `0.c0010_20260401_113235` | 9 | 9 | 0 | 0 | 0 | 6 | 3 | 9 | 4 | 5 |
| `0.c0011` | `0.c0011` | yes | `0.c0011_20260402_174921` | 11 | 11 | 0 | 0 | 0 | 4 | 7 | 11 | 9 | 2 |
| `0.c0012` | `0.c0012` | yes | `0.c0012_20260401_113242` | 3 | 3 | 0 | 0 | 0 | 3 | 0 | 3 | 2 | 1 |
| `0.c0013` | `0.c0013` | no | `0.c0013_20260401_113250` | 4 | 4 | 0 | 0 | 0 | 3 | 1 | 4 | 3 | 1 |
| `0.c0015` | `0.c0015` | yes | `0.c0015_20260401_113256` | 5 | 5 | 0 | 0 | 0 | 4 | 1 | 5 | 2 | 3 |
| `0.c0017` | `0.c0017` | yes | `0.c0017_20260401_113305` | 6 | 6 | 0 | 0 | 0 | 6 | 0 | 6 | 2 | 4 |
| `0.c0026` | `0.c0026` | yes | `0.c0026_20260401_113319` | 6 | 6 | 0 | 0 | 0 | 5 | 1 | 6 | 6 | 0 |
| `0.costaricto` | `0.costaricto` | yes | `0.costaricto_20260401_113325` | 10 | 10 | 0 | 0 | 0 | 4 | 6 | 10 | 8 | 2 |
| `0.operation_midnighteclipse` | `0.operation_midnighteclipse` | yes | `0.operation_midnighteclipse_20260402_141553` | 17 | 17 | 0 | 0 | 0 | 9 | 8 | 18 | 4 | 14 |
| `0.outer_space` | `0.outer_space` | yes | `0.outer_space_20260401_113345` | 8 | 8 | 0 | 0 | 0 | 3 | 5 | 8 | 6 | 2 |
| `0.salesforce_data_exfiltration` | `0.salesforce_data_exfiltration` | yes | `0.salesforce_data_exfiltration_20260402_141715` | 18 | 18 | 0 | 0 | 0 | 8 | 10 | 12 | 3 | 9 |
| `0.shadowray` | `0.shadowray` | yes | `0.shadowray_20260401_113404` | 10 | 10 | 0 | 0 | 0 | 9 | 1 | 10 | 4 | 6 |

## Pair Validation Exceptions

- `0.apt41_dust_full`: Fidelity mismatch for T1490: campaign expects adapted, SUT expects inspired
- `0.c0013`: Fidelity mismatch for T1055: campaign expects adapted, SUT expects inspired
