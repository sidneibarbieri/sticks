# Campaign Expansion Plan: 3 -> 10 Validated Pairs

## Current validated baseline

Validated pairs (Campaign↔SUT↔Executor↔Evidence):
1. `0.c0011` (11/11)
2. `0.lateral_test` (6/6)
3. `0.pikabot_realistic` (11/11)

## Selection criteria for +7 campaigns

Each added campaign must optimize:
1. **SUT cost** (single Linux target preferred)
2. **Methodological defensibility** (claims proportional to fidelity)
3. **Executable overlap** with currently implemented executors

## Executor coverage used as filter

Available executor techniques (current):
- `T1021.004`, `T1041`, `T1059.001`, `T1059.003`, `T1059.005`, `T1059.007`
- `T1078.001`, `T1083`, `T1190`, `T1204.001`, `T1204.002`
- `T1560.001`, `T1566.001`, `T1566.002`, `T1574`
- `T1583.001`, `T1587.003`, `T1608.001`

## Proposed +7 inspired campaigns (from corpus)

Selected from `software/sticks/data/caldera_adversaries` by overlap with executor coverage:

1. `0.c0010` — low-complexity infra + exploit staging
   - Candidate subset: `T1583.001`, `T1608.001`, `T1190`
2. `0.c0021` — phishing + script chain (compact)
   - Candidate subset: `T1583.001`, `T1566.002`, `T1204.001`, `T1059.001`
3. `0.operation_spalax` — phishing delivery chain
   - Candidate subset: `T1583.001`, `T1608.001`, `T1566.001`, `T1204.002`
4. `0.night_dragon` — exploit + execution + collection
   - Candidate subset: `T1190`, `T1059.003`, `T1083`, `T1608.001`
5. `0.arcanedoor` — exploit + discovery + exfil
   - Candidate subset: `T1190`, `T1083`, `T1041`, `T1587.003`
6. `0.water_curupira_pikabot_distribution` — user execution chain
   - Candidate subset: `T1566.001`, `T1204.001`, `T1204.002`, `T1059.007`
7. `0.c0017` — exploit + execution + exfil + hijack
   - Candidate subset: `T1190`, `T1059.003`, `T1041`, `T1574`

## Validation gate (campaign counted only if all pass)

A campaign only counts as validated when all are true:
- IaC up via canonical pipeline (`up_lab.sh`)
- Health checks pass or are logged with explicit limitations
- Campaign executes through `unified_campaign_runner.py`
- `summary.json` + `manifest` + per-technique evidence saved
- Failures/limitations documented without masking

## Known limitation policy

- No overclaim: partial technique execution is not "full campaign reproduced"
- Inspired/adapted labels bound the scope of claims
- Windows substrate only if it changes scientific inference materially
