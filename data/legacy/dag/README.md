# Historical technique inventory

These eight files preserve the technique occurrences from the historical
campaign DAGs. Each file records the SHA-256 of its original source and retains
only the technique IDs required for corpus-parity checks. The IDs retain source
order and multiplicity for reproducible comparison.

The inventory does not certify historical chronology, implemented procedures,
successful execution, or mechanism fidelity. Those claims require their own
execution and observation records.

Run `python scripts/audit_legacy_parity.py` from the artifact root to compare
this inventory with the current campaign files and SUT profiles. The auditor
requires no other checkout and writes reports under `runs/legacy-parity/`.
Use `--output-dir PATH` to select another report directory. Source reconciliation is an author-side check in
`tests/internal/test_paper_measurements.py`, which is excluded from reviewer
packages together with the author-side measurement generator.
