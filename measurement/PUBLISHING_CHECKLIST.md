# Publishing Checklist (Measurement + Datasets)

Use this checklist before pushing to GitHub.

## 1) Clean workspace artifacts
- Remove local editor/OS noise (`.DS_Store`, temporary LaTeX outputs outside manuscript directory).
- Ensure exploratory pilot outputs are not present in canonical results.

## 2) Rebuild canonical outputs
From repository root:

```bash
bash measurement/sut/release_check.sh
```

Expected: `PASS: pipeline + data + paper build are consistent`

## 3) Validate canonical dataset scope
Required outputs under `measurement/sut/scripts/results/`:
- `todo_values.json`
- `todo_values_latex.tex`
- `figures_data.json`
- `claim_evidence_map.csv`
- `audit/*.csv` (canonical audit set documented in `measurement/sut/README.md`)

## 4) Validate manuscript coupling
- `ACM CCS - Paper 2/main.tex` must import generated macros from:
  - `../measurement/sut/scripts/results/todo_values_latex.tex`
- Figure templates in `ACM CCS - Paper 2/figs/` must be regenerated from `render_figures.py`.

## 5) Honesty / traceability gate
- No placeholder replaced by fabricated data.
- Claims tied to measurable outputs and covered by `measurement/sut/TRACEABILITY.md`.
- Deprecated/revoked filtering and CVE illustrative/actionable split remain enabled.

## 6) Final publish review
- No duplicate files with same role in different directories.
- No hidden local metadata files.
- Commit message clearly states whether changes are canonical or exploratory.
