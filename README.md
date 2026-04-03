# Environment Reproducibility Artifact

This staging directory contains the minimal reproducibility surface for
the environment-semantics measurement study in structured CTI.

Paper title: The Environment Semantics Gap in Structured CTI: Measuring SUT Requirements for APT Emulation.

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

This wrapper is the reviewer-facing entry point.
It jumps to the canonical verifier
(`sticks/measurement/sut/release_check.sh`) and reruns the full
measurement validation path.

This public review artifact intentionally focuses on the measurement and
validation path cited by the paper. Heavier lab-orchestration helpers
from the full development workspace are not required for reproducing
the reported measurement claims and are therefore not part of this
staged repository.

## What the reviewer can verify directly

- Retrieval: the repository is public, self-contained, and includes a `LICENSE`.
- Exercisability: `bash run_review_check.sh` drives the full reviewer path end to end.
- Main-result reproduction: the command refreshes the released measurement outputs
  and verifies that the generated values remain consistent with the released reports.

## Runtime expectations

- Python 3.11+
- A TeX environment with `latexmk`/`pdflatex` available
- Poppler tools (`pdftoppm`, `pdfinfo`) available on `PATH`
- Rough runtime on a laptop-class machine: about 40 seconds for the full check
- No network access, API keys, Caldera, or container runtime required once cloned

## Repository layout

- `run_review_check.sh`: root-level wrapper for the reviewer path.
- `sticks/measurement/sut/`: measurement code, verifier, docs, and audit-facing data.
- `sticks/scripts/`: shared helper scripts used by the verifier.
- `sticks/measurement/sut/scripts/results/`: generated audit outputs refreshed by the verifier.
- `sticks/results/`: generated manuscript-sync reports refreshed by the verifier.

## What is intentionally included

- The measurement pipeline and figure/traceability generators.
- The five bundle snapshots used by the paper.
- The output synchronizer used by `release_check.sh` when a private manuscript tree is present.

## What is intentionally excluded

- Private manuscript trees and submission-specific files.
- Optional Caldera or runtime orchestration material not required for the measurement claims.
- Workspace-local temporary files, historical logs, and exploratory side outputs.

The goal is auditability with minimal reviewer friction.
