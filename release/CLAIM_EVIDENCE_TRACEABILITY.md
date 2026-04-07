# Claim-to-Evidence Traceability

Auto-generated from canonical release artifacts.

| Claim ID | Claim | Measured Value | Evidence Artifacts |
|---|---|---|---|
| CLAIM-PAIR-01 | Published campaign-SUT pair consistency validated by the loader. | 12/14 pairs valid | `release/campaign_sut_fidelity_matrix.json`, `src/loaders/campaign_loader.py` |
| CLAIM-EXEC-01 | Latest execution evidence shipped in the current artifact checkout shows successful completion without failed techniques. | 2/2 available campaign snapshots with failed=0 | `release/campaign_sut_fidelity_matrix.json` |
| CLAIM-RUBRIC-01 | Rubric computed fidelity remains consistent with declared fidelity. | consistent=58/125, mismatches=67 | `release/fidelity_report.json`, `release/fidelity_tables.tex`, `sticks/data/abilities_registry/fidelity_rubric.py` |
| CLAIM-FULLLAB-01 | Representative VM-backed cold-start workflow status. | 2/2 representative VM-backed runs PASS | `release/evidence/health_<campaign>_<timestamp>.json`, `release/evidence/<campaign>_<timestamp>/summary.json` |
