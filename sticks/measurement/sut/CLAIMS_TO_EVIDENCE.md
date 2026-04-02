# Claims to Evidence Mapping

This file maps the main empirical claims of Paper 2 to the concrete artifacts
that reviewers can inspect or regenerate.

## Core Claims

| Claim | Artifact evidence | How it is checked |
|-------|-------------------|-------------------|
| Platform fields are near-universal, but software and CVE evidence are much sparser | `scripts/results/todo_values.json`, `scripts/results/audit/platform_distribution.csv`, `scripts/results/figures_data.json` | `release_check.sh` reruns `sut_measurement_pipeline.py` and validates key invariants |
| Campaign-level platform inference remains partially unknown under conservative rules | `scripts/results/audit/campaign_platforms_software_only.csv`, `scripts/results/audit/campaign_platform_unknown.csv`, `scripts/results/audit/campaign_os_family_counts.csv` | static-table and list checks inside `release_check.sh` |
| Software references rarely provide replay-ready specificity | `scripts/results/audit/campaign_software.csv`, `scripts/results/figures_data.json`, `ACM CCS - Paper 2/figures/software_specificity_template.tex` | figure regeneration plus manuscript rebuild |
| Campaign-level CVE signal is rare and unevenly useful | `scripts/results/audit/campaign_cves.csv`, `scripts/results/audit/is_cves.csv`, `scripts/results/audit/all_cves.csv` | static-table checks for campaign-linked CVEs and CVE-profile outcomes |
| Most Enterprise techniques are not container-feasible | `scripts/results/audit/technique_compatibility.csv`, `scripts/results/audit/compatibility_rule_breakdown.csv`, `scripts/results/audit/compatibility_default_sensitivity.csv` | numeric invariants plus rule-breakdown checks in `release_check.sh` |
| Profile ambiguity remains high at low evidence density and collapses by `k >= 2` linked software items | `scripts/results/audit/profile_specificity_software_only.csv`, `scripts/results/audit/profile_ablation_summary.csv`, `scripts/results/audit/evidence_threshold_curve.csv`, `scripts/results/audit/delta_sensitivity.csv`, `scripts/results/audit/bootstrap_confusion_distribution.csv` | threshold, bootstrap, and delta-sensitivity invariants in `release_check.sh` |
| The manuscript is synchronized with the measured outputs | `ACM CCS - Paper 2/results/values.tex`, `scripts/results/todo_values_latex.tex`, `TRACEABILITY.md` | `sync_manuscript_values.py`, figure regeneration, traceability generation, and PDF rebuild |

## Honest Non-Claims

The artifact does **not** claim:

- faithful replay of historical intrusions,
- end-to-end automated SUT provisioning from CTI alone,
- actor-specific attribution from environment profiles,
- independent execution-ground-truth validation for every compatibility class.

## Canonical Reviewer Entry Point

```bash
bash run_review_check.sh

# direct equivalent inside the workspace / packaged tree
cd sticks/measurement/sut
bash release_check.sh
```

The root wrapper is the smoothest reviewer-facing path. The canonical
`release_check.sh` behind it is the reproducibility contract for this paper.

## Reviewer-Facing Assumptions

- The artifact is self-contained after clone; no network fetch is required.
- The measurement claims do not depend on Caldera, Docker, or any runtime
  emulation substrate.
- The shipped PDF at `ACM CCS - Paper 2/main.pdf` is the same manuscript that
  `release_check.sh` rebuilds from the local bundles and generated outputs.
