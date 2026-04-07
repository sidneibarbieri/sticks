# Claim-to-Evidence Traceability

Auto-generated from canonical release artifacts.

| Claim ID | Claim | Measured Value | Evidence Artifacts |
|---|---|---|---|
| CLAIM-PAIR-01 | Published campaign-SUT pair consistency validated by the loader. | 12/14 pairs valid | `release/campaign_sut_fidelity_matrix.json`, `src/loaders/campaign_loader.py` |
| CLAIM-EXEC-01 | Latest execution snapshot shows successful completion without failed techniques. | 14/14 campaigns with failed=0 | `release/campaign_sut_fidelity_matrix.json` |
| CLAIM-RUBRIC-01 | Rubric computed fidelity remains consistent with declared fidelity. | consistent=58/125, mismatches=67 | `release/fidelity_report.json`, `release/fidelity_tables.tex`, `sticks/data/abilities_registry/fidelity_rubric.py` |
| CLAIM-FULLLAB-01 | Full-lab batch workflow status (canonical scripts). | 2/2 campaigns PASS | `release/full_lab_batch_20260320_010509.tsv` |
