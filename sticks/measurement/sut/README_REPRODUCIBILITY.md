# Reproduction Guide - Environment Semantics Gap Artifact

## Canonical Reviewer Path

In the packaged review artifact, the smoothest reviewer-facing command is:

```bash
bash run_review_check.sh
```

That wrapper enters `sticks/measurement/sut` and invokes the canonical verifier. In the workspace tree, the direct equivalent is:

```bash
cd sticks/measurement/sut
bash release_check.sh
```

The paper now points reviewers to the wrapper first and names `sticks/measurement/sut/release_check.sh`
as the canonical script behind it. The verifier checks the local input bundles,
reruns the measurement pipeline, regenerates figure data and traceability files,
checks the numeric invariants used by the manuscript, validates static tables
against measured artifacts, enforces bibliography policy, and recompiles the PDF.
On the current laptop-class development machine, the full pass completes in about 40 seconds.

The review artifact is intentionally offline once cloned. It does not require
network access, API keys, Caldera, container runtimes, or any cyber-range
orchestration stack. All bundle snapshots needed by the measurements are
already included in `scripts/data/`.

## What This Artifact Proves

| Claim | Evidence |
|-------|----------|
| The reported counts are reproducible from local CTI bundles | `release_check.sh` reruns `sut_measurement_pipeline.py` and validates key invariants |
| The paper tables and figures are synchronized with measured outputs | manuscript sync + static-table checks in `release_check.sh` |
| Audit files exist for the main findings | `scripts/results/audit/` contains campaign/software/CVE/platform/profile/compatibility traces |
| The manuscript can be rebuilt from the released pipeline | `release_check.sh` recompiles Paper 2 after regeneration |

## What This Artifact Does NOT Prove

- Historical replay fidelity for real campaigns
- Fully automated SUT provisioning from CTI alone
- End-to-end offensive execution for every campaign in the corpus
- That optional runtime environments are required to reproduce the paper's measurements

## Artifact Boundary

The minimal review artifact for this paper should include only the components
required by `release_check.sh` plus the manuscript sources needed to rebuild the
PDF. Optional runtime, orchestration, or cyber-range material may exist in the
broader research workspace, but it is outside the reproducibility contract for
this measurement paper and should be excluded from the paper-scoped artifact.

For a fast read-before-run path, the artifact also ships the current manuscript
PDF at `ACM CCS - Paper 2/main.pdf`. Reviewers can inspect that file first and
then run the verifier if they want to reproduce the full path from bundle to PDF.

## Key Files

- `release_check.sh` - canonical one-command verifier
- `scripts/sut_measurement_pipeline.py` - main measurement pipeline
- `scripts/render_figures.py` - figure-data regeneration
- `scripts/generate_traceability.py` - traceability appendix generation
- `scripts/results/audit/` - audit CSVs referenced by the manuscript
- `CLAIMS_TO_EVIDENCE.md` - claim-to-artifact mapping
