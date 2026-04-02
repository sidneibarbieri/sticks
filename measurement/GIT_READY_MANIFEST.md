# Git-ready manifest

## Core manuscript
- `ACM CCS - Paper 2/main.tex`
- `ACM CCS - Paper 2/references_official_downloaded.bib`
- `ACM CCS - Paper 2/references.bib`
- `ACM CCS - Paper 2/figs/coverage_template.tex`
- `ACM CCS - Paper 2/figs/software_specificity_template.tex`
- `ACM CCS - Paper 2/figs/cve_location_template.tex`
- `ACM CCS - Paper 2/figs/jaccard_cdf_template.tex`

## Measurement software and data
- `measurement/sut/scripts/sut_measurement_pipeline.py`
- `measurement/sut/scripts/render_figures.py`
- `measurement/sut/scripts/generate_traceability.py`
- `measurement/sut/scripts/data/enterprise-attack.json`
- `measurement/sut/scripts/data/mobile-attack.json`
- `measurement/sut/scripts/data/ics-attack.json`
- `measurement/sut/scripts/data/stix-capec.json`
- `measurement/sut/scripts/data/fight-enterprise-10.1.json`
- `measurement/sut/scripts/results/todo_values.json`
- `measurement/sut/scripts/results/todo_values_latex.tex`
- `measurement/sut/scripts/results/figures_data.json`
- `measurement/sut/scripts/results/claim_evidence_map.csv`
- `measurement/sut/scripts/results/audit/*.csv` (canonical audit outputs listed in `measurement/sut/README.md`)
- `measurement/sut/README.md`
- `measurement/sut/TRACEABILITY.md`
- `measurement/sut/release_check.sh`

## Optional process docs
- `measurement/MEASUREMENT_DOD.md`
- `measurement/meta/*`

## Excluded from canonical release
- exploratory pilot outputs:
  - `measurement/sut/scripts/results/report_gap_pilot.json`
  - `measurement/sut/scripts/results/audit/report_gap_object_level.csv`
  - `measurement/sut/scripts/results/audit/report_gap_reference_level.csv`

## Validation command
From repository root:

```bash
./measurement/sut/release_check.sh
```

Expected result: `PASS: pipeline + data + paper build are consistent`
