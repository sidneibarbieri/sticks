# MITRE Scope and Realism Statement

This document defines the exact methodological scope of the STICKS artifact.

## 1) What Is MITRE-Aligned

The artifact is aligned to MITRE ATT&CK/STIX at the following levels:

- Campaign IDs (e.g., `C0010`, `C0011`) are preserved as explicit references.
- ATT&CK technique IDs are used as the operational unit in campaign steps.
- Campaign-to-SUT pairing is explicit and validated.
- Technique execution evidence is recorded per step.

## 2) What Is NOT Claimed

The artifact does **not** claim full faithful reproduction of complete original ATT&CK campaigns.

Specifically:

- It does not claim that every procedure in the original campaign narrative was reproduced.
- It does not claim wild-environment execution.
- It does not claim Windows-native mechanisms were faithfully reproduced on Linux substrate.

## 3) Execution Fidelity Model (Project Taxonomy)

The artifact uses an explicit fidelity taxonomy:

- `faithful`: mechanism and substrate are preserved.
- `adapted`: mechanism preserved with controlled substrate adaptation.
- `inspired`: intent preserved, mechanism/substrate diverges.

This is the STICKS methodological taxonomy and is reported per technique with rubric evidence.

## 4) Lab Realism Boundaries

The experiments are designed as controlled lab executions.

- Preconditions (credentials, weaknesses, files) can be pre-staged by SUT profiles.
- This improves reproducibility and auditability.
- It also bounds inference compared to uncontrolled real-world operations.

These boundaries are documented as limitations in campaign evidence and rubric outputs.

## 5) What Was Demonstrated (Current Release)

For the current formal set of 10 campaigns:

- Campaign-SUT pair consistency is validated.
- Full-lab batch execution completed for all 10 with `PASS` status.
- Latest campaign snapshots show `failed=0`.
- Per-technique fidelity reports and LaTeX tables are generated from evidence.

Canonical artifacts:

- `release/full_lab_batch_20260315_015321.tsv`
- `release/campaign_sut_fidelity_matrix.json`
- `release/CAMPAIGN_SUT_FIDELITY_MATRIX.md`
- `release/fidelity_report.json`
- `release/fidelity_tables.tex`
- `release/CLAIM_EVIDENCE_TRACEABILITY.md`

## 6) Reviewer Guidance

Reviewers should interpret results as:

- Reproducible execution of formal inspired/adapted profiles derived from MITRE references.
- Not as complete replay of all procedures in original ATT&CK campaign records.

This statement is intentionally strict to preserve methodological honesty.
