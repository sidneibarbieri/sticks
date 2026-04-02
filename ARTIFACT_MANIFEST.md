# Complete Public Artifact Manifest

Public repository URL: `https://github.com/sidneibarbieri/sticks`.

## Included

- Full STICKS code needed for the canonical smoke path.
- VM-backed lab helpers and SUT-application code used for realism checks.
- Current synthesized release/results reports used to ground paper claims.
- The Paper 2 manuscript source and current built PDF.

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
