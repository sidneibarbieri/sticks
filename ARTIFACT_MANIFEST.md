# Artifact Manifest

Suggested repository name: `sticks`.

Public repository URL: `https://github.com/sidneibarbieri/sticks`.

## Included components

- `run_review_check.sh`: root-level reviewer entrypoint.
- `sticks/measurement/sut/release_check.sh`: canonical verifier called by the paper-cited wrapper.
- `sticks/measurement/sut/scripts/`: only the scripts required by the verifier.
- `sticks/measurement/sut/scripts/data/`: the five STIX/ATT&CK-related bundle snapshots used in the measurements.
- `sticks/scripts/sync_manuscript_values.py`: optional manuscript synchronization helper for private workspace use.

## Excluded components

- Private manuscript sources and submission-specific assets.
- Optional runtime and cyber-range execution tooling.
- Large historical result archives and host-specific temporary outputs.

## Reproduction contract

If `bash run_review_check.sh` passes from the repository root, the staged artifact has
enough material to rerun the measurement pipeline, regenerate tables/figures,
and refresh the released audit outputs.

The intended publication surface for this repository is the tagged public revision
of the artifact itself. If a DOI-backed archival snapshot is later created, it should
point to the same tagged contents.
