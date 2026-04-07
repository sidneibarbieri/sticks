# Paper-Ready Summary

Scope:
- `values.tex` and related macros summarize the latest execution evidence currently shipped in the artifact checkout.
- `results/CORPUS_STATE.md` remains the source for statements about the broader published corpus and pair-valid coverage.
- Missing execution evidence is shown explicitly; it is not silently counted as a failed or successful run.

Generated files:
- `release/campaign_sut_fidelity_matrix.json`
- `release/CAMPAIGN_SUT_FIDELITY_MATRIX.md`
- `release/fidelity_report.json`
- `release/fidelity_tables.tex`
- `release/claim_evidence_traceability.json`
- `release/CLAIM_EVIDENCE_TRACEABILITY.md`
- `release/paper_ready_macros.tex`
- `release/values.tex`
- `release/full_lab_status_table.tex`
- `release/CLAIMS_FOR_PAPER.md`

Top-level measured claims:
- `CLAIM-PAIR-01`: 12/14 pairs valid
- `CLAIM-EXEC-01`: 2/2 available campaign snapshots with failed=0
- `CLAIM-RUBRIC-01`: consistent=58/125, mismatches=67
- `CLAIM-FULLLAB-01`: 2/2 representative VM-backed runs PASS
