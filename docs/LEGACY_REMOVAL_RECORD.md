# Legacy Removal Record

Date: 2026-03-18

The root-level `legacy/` directory was reviewed before removal.

Decision summary:

- Preserved as reference:
  - reviewer-oriented definition-of-done criteria
  - reproducibility-gap checklist
  - historical standalone SUT profile checker
- Not preserved:
  - wrapper scripts already superseded by canonical entry points
  - archived review drafts and manuscript-support files
  - tarballs and duplicated release packages
  - root-level historical noise unrelated to the software artifact

Preserved material now lives in:

- `docs/legacy_preserved/`

Rationale:

- keep the current artifact small and reviewer-friendly
- preserve methodological lessons without reintroducing obsolete entry points
- remove ambiguous or duplicate execution surfaces
