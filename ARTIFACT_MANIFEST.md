# Artifact Manifest

Suggested repository name: `sticks`.

Public repository URL: `https://github.com/sidneibarbieri/sticks`.

## Included components

- `run_review_check.sh`: root-level reviewer entrypoint.
- `ACM CCS - Paper 2/`: manuscript source, bibliography, class/bst files, rendered figure templates, and `results/values.tex`.
- `sticks/measurement/sut/release_check.sh`: canonical verifier called by the paper-cited wrapper.
- `sticks/measurement/sut/scripts/`: only the scripts required by the verifier.
- `sticks/measurement/sut/scripts/data/`: the five STIX/ATT&CK-related bundle snapshots used in the measurements.
- `sticks/scripts/sync_manuscript_values.py`: Paper-2-only macro synchronization helper.

## Excluded components

- Paper 1 manuscript sources and analysis pipeline.
- Optional runtime and cyber-range execution tooling.
- Large historical result archives and host-specific temporary outputs.

## Reproduction contract

If `bash run_review_check.sh` passes from the repository root, the staged artifact has
enough material to rerun the measurement pipeline, regenerate tables/figures,
synchronize manuscript values, and rebuild the Paper 2 PDF.
