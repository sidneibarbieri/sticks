# Corpus State

- Generated at: `2026-04-02T17:58:40.182827`
- Published campaigns: `14`
- Executable campaigns with SUT profile: `14`
- Campaign/SUT pairs passing strict validation: `12`
- Campaigns with latest evidence: `14`
- Campaigns with zero failed techniques in latest evidence: `14`
- Campaigns with clean MITRE metadata audit: `14`
- Campaigns without host leakage in latest evidence: `14`
- Legacy direct counterparts: `8`
- Legacy exact technique matches: `0.apt41_dust, 0.c0010, 0.c0026, 0.costaricto, 0.operation_midnighteclipse, 0.outer_space, 0.salesforce_data_exfiltration, 0.shadowray`
- Legacy technique coverage rate: `100.0%`

## Campaign Status

| Campaign | SUT | Pair Valid | Evidence | Latest Success | MITRE Clean | Host Leakage | Legacy Match |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0.apt41_dust | yes | yes | yes | 23/23 (100.0%) | yes | no | exact |
| 0.apt41_dust_full | yes | no | yes | 10/10 (100.0%) | yes | no | n/a |
| 0.c0010 | yes | yes | yes | 9/9 (100.0%) | yes | no | exact |
| 0.c0011 | yes | yes | yes | 11/11 (100.0%) | yes | no | n/a |
| 0.c0012 | yes | yes | yes | 3/3 (100.0%) | yes | no | n/a |
| 0.c0013 | yes | no | yes | 4/4 (100.0%) | yes | no | n/a |
| 0.c0015 | yes | yes | yes | 5/5 (100.0%) | yes | no | n/a |
| 0.c0017 | yes | yes | yes | 6/6 (100.0%) | yes | no | n/a |
| 0.c0026 | yes | yes | yes | 6/6 (100.0%) | yes | no | exact |
| 0.costaricto | yes | yes | yes | 10/10 (100.0%) | yes | no | exact |
| 0.operation_midnighteclipse | yes | yes | yes | 17/17 (100.0%) | yes | no | exact |
| 0.outer_space | yes | yes | yes | 8/8 (100.0%) | yes | no | exact |
| 0.salesforce_data_exfiltration | yes | yes | yes | 18/18 (100.0%) | yes | no | exact |
| 0.shadowray | yes | yes | yes | 10/10 (100.0%) | yes | no | exact |

## Validation Exceptions

- `0.apt41_dust_full`: Fidelity mismatch for T1490: campaign expects adapted, SUT expects inspired
- `0.c0013`: Fidelity mismatch for T1055: campaign expects adapted, SUT expects inspired