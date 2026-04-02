# Claims for Paper Text

Use these measured statements directly in Results/Artifact sections.

## CLAIM-PAIR-01
- Claim: Published campaign-SUT pair consistency validated by the loader.
- Measured value: 12/14 pairs valid
- Evidence:
  - `release/campaign_sut_fidelity_matrix.json`
  - `src/loaders/campaign_loader.py`

## CLAIM-EXEC-01
- Claim: Latest execution snapshot shows successful completion without failed techniques.
- Measured value: 14/14 campaigns with failed=0
- Evidence:
  - `release/campaign_sut_fidelity_matrix.json`

## CLAIM-RUBRIC-01
- Claim: Rubric computed fidelity remains consistent with declared fidelity.
- Measured value: consistent=58/125, mismatches=67
- Evidence:
  - `release/fidelity_report.json`
  - `release/fidelity_tables.tex`
  - `sticks/data/abilities_registry/fidelity_rubric.py`

## CLAIM-FULLLAB-01
- Claim: Full-lab batch workflow status (canonical scripts).
- Measured value: 2/2 campaigns PASS
- Evidence:
  - `release/full_lab_batch_20260320_010509.tsv`
