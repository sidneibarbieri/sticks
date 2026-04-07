# Reviewer Summary

## Canonical Reviewer Path

```bash
./artifact/setup.sh
./artifact/run.sh
./artifact/validate.sh
```

This path is the reviewer baseline. It is intentionally narrower than the full
published corpus.

## What The Reviewer Can Trust

- `0.c0011` is the current canonical smoke-path campaign.
- ATT&CK metadata consistency is audited against the local Enterprise bundle.
- Evidence is written under `release/evidence/`.
- Tables are generated under `results/tables/`.

## Important Distinctions

- Published corpus:
  - `campaigns/*.json`
- Executable subset:
  - published campaigns that also have `data/sut_profiles/<campaign>.yml`
- Latest execution status:
  - `results/CORPUS_STATE.md`
- Migration status versus `sticks-docker`:
  - `results/LEGACY_PARITY_REPORT.md`

## Honesty Rule

Reviewer-facing text should rely on:

- `results/CORPUS_STATE.md`
- `results/MITRE_METADATA_AUDIT.md`
- `results/LEGACY_PARITY_REPORT.md`

and not on historical frozen summaries that were generated from older repository states.
