# Artifact Evaluation Guide

This document mirrors the current public reviewer contract for the STICKS
artifact. Use it when you want one place that states the supported execution
paths, host expectations, and evidence locations without reading the whole
repository.

## Supported Paths

| Path | Command | Required tools | Recommended host | Purpose |
| --- | --- | --- | --- | --- |
| Fast validation | `bash run_review_check.sh` | `python3`, `venv` | commodity laptop/desktop | revalidate released values and paper-facing outputs |
| Minimal working example | `./artifact/setup.sh && ./artifact/run.sh && ./artifact/validate.sh` | `python3`, `venv` | commodity laptop/desktop | smallest live execution trace |
| VM-backed realism | `bash run_vm_backed_campaign.sh 0.c0011` | `python3`, `venv`, `vagrant`, `qemu` or `libvirt` | 8 CPU cores, 16 GB RAM, 25 GB free disk recommended | cold-start campaign/SUT replay on declared lab infrastructure |

The first two paths are the canonical reviewer contract. The VM-backed path is
supported, but intentionally heavier.

## Recommended Order

1. Run `bash run_review_check.sh`.
2. Run the `artifact/` smoke path if you want a live repository-local example.
3. Run `bash run_vm_backed_campaign.sh <campaign>` only when you want explicit
   substrate evidence from the declared lab environment.

## Fast Validation

```bash
bash run_review_check.sh
```

This reruns the measurement pipeline, refreshes paper-facing synthesized
outputs, and checks that the released values remain internally consistent.
It also regenerates the deterministic downstream CVE concretization report in
`results/CVE_RESOLUTION_CANDIDATES.md`.
That report is intentionally narrower than the paper claim: it is not an
exhaustive crawl of the `apt` or `pip` ecosystems, only a deterministic
resolution layer over ATT&CK-linked campaign/CVE pairs in the current artifact.
It also regenerates the compatibility-rule audit surface in
`results/COMPATIBILITY_RULE_SURFACE.md`.
It also regenerates the infrastructure/SUT automation coverage report in
`results/INFRA_AUTOMATION_COVERAGE.md`.

## Minimal Working Example

```bash
./artifact/setup.sh
./artifact/run.sh
./artifact/validate.sh
```

This path currently executes one representative campaign and emits structured
evidence under `release/evidence/`.

Equivalent direct commands:

```bash
python3 scripts/run_campaign.py --campaign 0.c0011
python3 scripts/generate_tables.py
```

## VM-Backed Realism

Representative cold-start runs:

```bash
bash run_vm_backed_campaign.sh 0.c0011
bash run_vm_backed_campaign.sh 0.shadowray
```

This path lifts the VM topology declared by the campaign's SUT profile, applies
the declared base SUT profile, optionally applies step-conditioned SUT overlays
for selected techniques, executes the campaign, refreshes evidence/state
reports, and tears the lab down unless `--keep-lab` is requested.

Important interpretation notes:

- The repository derives a static lower-bound SUT profile from one corpus
  snapshot and then runs a declared campaign/SUT pair.
- Selected techniques may apply declared SUT overlays at runtime, but those
  overlays are explicit campaign metadata rather than online CTI inference.
- The VM-backed path may provision and health-check a Caldera node inside the
  lab, but campaign execution is still driven by the STICKS runner, not by the
  `sticks-docker` atomic planner.
- A cold-start VM-backed run may be slow because guest bootstrap, package
  installation, and service provisioning happen inside the guests.

Backend preference:

- Linux x86_64: `libvirt`
- macOS ARM64: `qemu`

## Expected Outputs

The supported workflows write reviewer-visible evidence under:

```text
release/evidence/<campaign>_<timestamp>/
```

The most important files are:

- `summary.json`
- `manifest.json`
- `results/CORPUS_STATE.md`
- `results/CAMPAIGN_SUT_FIDELITY_MATRIX.md`
- `results/CVE_RESOLUTION_CANDIDATES.md`
- `results/cve_resolution_candidates.json`
- `results/COMPATIBILITY_RULE_SURFACE.md`
- `results/compatibility_rule_surface.json`
- `results/INFRA_AUTOMATION_COVERAGE.md`
- `results/infra_automation_coverage.json`
- `results/tables/corpus_table.tex`
- `results/tables/fidelity_table.tex`
- `results/tables/execution_table.tex`

## Troubleshooting

If Python imports fail:

```bash
export PYTHONPATH="$PWD/src:$PYTHONPATH"
```

If you want to audit the repository surface before sharing it:

```bash
python3 scripts/check_public_surface.py
```

If the VM-backed path reports degraded state, treat that as an infrastructure
signal first rather than assuming the campaign runner is wrong.
