# Complete Public Artifact Manifest

Public repository URL: `https://github.com/sidneibarbieri/sticks`.

## Included

- Full STICKS code needed for the canonical smoke path.
- VM-backed lab helpers and SUT-application code used for realism checks.
- Current synthesized release/results reports used to ground paper claims.
- Current synthesized outputs and generated reports needed for reproduction.
- Root-level wrappers for fast validation and one-command VM-backed runs.

## Reviewer-facing commands

- `bash run_review_check.sh`: fast paper-claim validation.
- `./artifact/setup.sh && ./artifact/run.sh && ./artifact/validate.sh`:
  minimal working example for repository-local execution.
- `bash run_vm_backed_campaign.sh 0.c0011`: representative VM-backed run.

## Excluded on purpose

- Local `.vagrant/` state.
- QEMU runtime overlays and cached base images.
- Generated cloud-init runtime artifacts.
- Developer-local Caldera config at `measurement/sut/caldera_conf/local.yml`.
- Developer-local `.env` and `measurement/meta/` residue.
- Raw `results/evidence`, `results/frozen`, and `release/evidence` trees.
- Python caches and local scratch files.

The goal is a complete public artifact for reproduction and inspection,
without publishing heavyweight local VM state or developer-only residue.
