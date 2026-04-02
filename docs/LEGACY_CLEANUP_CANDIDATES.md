# Legacy Cleanup Candidates (Phase 2)

This list tracks files/directories that are no longer canonical and are candidates
for archive/removal after one final validation cycle.

## Low-Risk (Safe to Archive Soon)

- `artifact/artifact_up.sh` (now wrapper only)
- `destroy.sh` (wrapper only)
- `reset.sh` (wrapper only)

## Medium-Risk (Keep, but mark as legacy)

- `local_campaign_runner.py` (local simulation mode)
- `sticks/lib/run_campaign.py` (old Caldera-oriented execution path)
- `sticks/lib/run_batch.py`
- `sticks/lib/run_batch_deterministic.py`

## High-Risk / Needs Dependency Audit

- `measurement/sut/scripts/` (large historical measurement pipeline family)
  - Contains many generators/analyzers with possible paper dependencies.
  - Do not remove without grep-based dependency map against:
    - `ACM CCS - Paper 1/`
    - `ACM CCS - Paper 2/`
    - `Makefile`
    - root scripts.

## Canonical Must-Keep

- `run_campaign.sh`
- `up_lab.sh`
- `unified_campaign_runner.py`
- `collect_evidence.sh`
- `destroy_lab.sh`
- `sticks/data/abilities_registry/`
- `sticks/data/campaigns/`
- `lab/sut_profiles/`
- `release/evidence/` (runtime output)

## Next Action (recommended)

1. Archive medium-risk legacy files into `legacy/` with compatibility stubs.
2. Run canonical smoke test:
   - `./run_campaign.sh 0.c0011`
   - `./collect_evidence.sh`
3. If green, proceed with dependency audit of `measurement/sut/scripts/`.
