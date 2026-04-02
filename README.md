# Paper 2 Review Artifact

This staging directory contains the minimal reproducibility surface for
the Paper 2 measurement manuscript on environment semantics in structured CTI.

Suggested public repository name: `sticks`.

## Public clone path

```bash
git clone https://github.com/sidneibarbieri/sticks.git
cd sticks
bash run_review_check.sh
```

```bash
bash run_review_check.sh
```

This wrapper is the reviewer-facing entry point used by the paper.
It jumps to the canonical verifier
(`sticks/measurement/sut/release_check.sh`) and reruns the full
measurement-to-manuscript validation path.

## Runtime expectations

- Python 3.11+
- A TeX environment with `latexmk`/`pdflatex` available
- Poppler tools (`pdftoppm`, `pdfinfo`) available on `PATH`
- Rough runtime on a laptop-class machine: about 40 seconds for the full check
- No network access, API keys, Caldera, or container runtime required once cloned

## Repository layout

- `run_review_check.sh`: root-level wrapper for the reviewer path.
- `ACM CCS - Paper 2/`: manuscript source plus the current built PDF.
- `sticks/measurement/sut/`: measurement code, verifier, docs, and audit-facing data.
- `sticks/scripts/`: manuscript sync/build helpers used by the verifier.
- `sticks/measurement/sut/scripts/results/`: generated audit outputs refreshed by the verifier.
- `sticks/results/`: generated manuscript-sync reports refreshed by the verifier.

## What is intentionally included

- The Paper 2 manuscript sources needed to rebuild the PDF.
- The current built manuscript PDF for read-before-run inspection.
- The measurement pipeline and figure/traceability generators.
- The five bundle snapshots used by the paper.
- The manuscript-value synchronizer used by `release_check.sh`.

## What is intentionally excluded

- Paper 1 sources and results.
- Optional Caldera or runtime orchestration material not required for the measurement claims.
- Workspace-local temporary files, historical logs, and exploratory side outputs.

The goal is auditability with minimal reviewer friction.
