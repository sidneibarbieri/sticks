# Reproducibility Notes

## Scope

This repository supports controlled campaign execution and evidence collection.
The current reproducibility target has three layers: a fast paper-claim
validation path, a repository-local minimal working example, and a supported
provider-aware VM-backed path for campaign/SUT pairs that need concrete lab
infrastructure.

## Fast Paper-Claim Validation

```bash
bash run_review_check.sh
```

This path reruns the measurement pipeline, regenerates reviewer-facing outputs,
and checks that the released values remain consistent from the same checkout.

## Minimal Working Example

```bash
./artifact/setup.sh
./artifact/run.sh
./artifact/validate.sh
```

The smoke path currently executes one representative campaign:

- `0.c0011`

and then regenerates the LaTeX tables used by the paper-facing workflow.

## Generated Outputs

The smoke path writes:

- `release/evidence/<campaign>_<timestamp>/summary.json`
- `release/evidence/<campaign>_<timestamp>/manifest.json`
- `results/tables/corpus_table.tex`
- `results/tables/fidelity_table.tex`
- `results/tables/execution_table.tex`

Supporting state reports can be regenerated with:

```bash
python3 scripts/generate_corpus_state.py
python3 scripts/audit_mitre_metadata.py
python3 scripts/audit_legacy_parity.py
python3 scripts/check_public_surface.py
```

For a concrete VM-backed run that provisions the declared SUT automatically:

```bash
bash run_vm_backed_campaign.sh 0.c0011
bash run_vm_backed_campaign.sh 0.shadowray
```

That wrapper delegates to `scripts/run_lab_campaign.py`, which lifts the VM
substrate declared by the campaign's SUT profile, applies the declared base SUT
profile, applies step-conditioned SUT overlays for selected techniques,
executes the campaign, refreshes evidence/state reports, and tears the lab down
unless `--keep-lab` is requested.

The interpretation is intentionally conservative: the repository derives a
static lower-bound SUT profile from one corpus snapshot and then runs a
declared campaign/SUT pair. It does not perform online replanning or choose
final vulnerabilities/commands dynamically during execution; the step-level
overlays are explicit campaign metadata rather than new inference.

## Optional Infrastructure

Provider-aware lab helpers exist for broader infrastructure experiments and
realism checks:

- `scripts/up_lab.sh`
- `scripts/destroy_lab.sh`
- `multi_vm_manager_2vm.py`

These helpers are supported, but they are intentionally heavier than the smoke
path and should be interpreted campaign by campaign rather than as a promise of
historical replay fidelity.

Backend preference for the optional VM-backed path is currently:

- `libvirt` on Linux
- `qemu` on macOS ARM64

This is an implementation detail of the optional infrastructure layer, not a
requirement for the canonical smoke path.

## Known Limits

- Some campaigns still expose missing executor coverage or unmet semantic
  preconditions at the strict pair-validation level even when a profile file is
  present.
- Compatibility JSON campaigns and canonical YAML campaigns coexist in the same
  repository; the loader supports both.
- Raw evidence is generated locally under `release/evidence/` when a reviewer
  runs the included workflows.
- The public GitHub handoff keeps synthesized reports, not heavyweight frozen
  evidence trees.

## Integrity Principle

The repository should not claim universal success where the current execution
path still reports real failures. Reviewer-facing instructions should therefore
start from `run_review_check.sh`, then widen to the repository-local example,
and only then to the VM-backed path when explicit substrate evidence matters.
