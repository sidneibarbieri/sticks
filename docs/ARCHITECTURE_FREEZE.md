# Architecture Freeze (Pre-Full-Lab Validation)

## Scope freeze

From this point until completion of full-lab validation for the representative set,
no structural renaming or directory moves should be performed.

## Canonical software root

- `software/`

## Canonical runtime flow

1. `./setup.sh`
2. `./run_campaign.sh <campaign_id> [--provider ...]`
3. `./collect_evidence.sh`
4. `./destroy_lab.sh`

(Root scripts are thin wrappers to `software/`.)

## Canonical data contract

- Campaign definitions: `software/sticks/data/campaigns/*.yml`
- SUT profiles: `software/lab/sut_profiles/*.yml`
- Executor registry: `software/sticks/data/abilities_registry/executor_registry.py`
- Evidence output: `software/release/evidence/<campaign_timestamp>/`

## Validation set (full-lab, zero-touch)

- `0.c0011`
- `0.lateral_test`
- `0.pikabot_realistic`
- `0.c0010`
- `0.c0021`

## Acceptance gate per campaign

A campaign counts as full-lab validated only if all conditions hold:
- IaC provisioning succeeds via canonical command
- health check runs and report is generated
- SUT profile is applied automatically
- campaign execution produces `summary.json` and `per_technique` evidence
- limitations/failures are recorded without masking
- teardown works (`destroy_lab.sh`)
