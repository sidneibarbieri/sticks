# Reviewer Guide

This guide keeps the reviewer path short and explicit.

## Host Expectations

| Path | Required tools | Recommended host | Notes |
| --- | --- | --- | --- |
| `run_review_check.sh` | `python3`, `venv` | commodity laptop/desktop | fastest way to validate paper-facing outputs |
| `artifact/` smoke path | `python3`, `venv` | commodity laptop/desktop | smallest repository-local execution trace |
| `run_vm_backed_campaign.sh` | `python3`, `venv`, `vagrant`, `qemu` or `libvirt` | 8 CPU cores, 16 GB RAM, 25 GB free disk recommended | cold-start guest bootstrap can dominate runtime |

For the heavy path, Linux x86_64 with `libvirt` is preferred when available.
On macOS ARM64, the supported fallback is `qemu`.

## Recommended Order

1. Run the fast paper-claim validation path.
2. Run the repository-local minimal working example if you want the smallest execution trace.
3. If you want the realistic VM-backed substrate, run the canonical lab path.

## 1. Fast Paper-Claim Validation

```bash
bash run_review_check.sh
```

This path is the fastest way to revalidate the released measurement outputs and
paper-facing synthesized artifacts.

## 2. Minimal Working Example

```bash
./artifact/setup.sh
./artifact/run.sh
./artifact/validate.sh
```

Expected outputs:

- `release/evidence/<campaign>_<timestamp>/summary.json`
- `release/evidence/<campaign>_<timestamp>/manifest.json`
- `results/tables/corpus_table.tex`
- `results/tables/fidelity_table.tex`
- `results/tables/execution_table.tex`

## 3. Direct Commands

If you prefer not to use the wrappers:

```bash
python3 scripts/run_campaign.py --campaign 0.c0011
python3 scripts/generate_tables.py
```

To list campaigns:

```bash
python3 scripts/run_campaign.py
```

To audit the reviewer-facing repository surface:

```bash
python3 scripts/check_public_surface.py
```

This audit checks for stale reviewer paths, duplicate documentation
directories, and local runtime residue that should not survive into a clean
artifact handoff.

## 4. VM-Backed Realism Path

The repository also contains a provider-aware VM-backed path for realism
checks. This path is not required for the smoke path, but it is the supported
way to validate the QEMU/libvirt-backed substrate.

Important:

- The smoke path does not depend on QEMU or Caldera being green.
- The smoke path does not require a specific host platform or hypervisor.
- The preferred VM-backed backend is `libvirt` on Linux and `qemu` on macOS ARM64.
- A cold-start VM-backed run can take materially longer than the smoke path
  because the guests may need first-boot package installation and service
  provisioning before campaign execution starts.
- VM-backed claims should be based on a fresh run of the canonical lab path in
  the same checkout.
- The VM-backed unit of validation is a single self-contained campaign/SUT pair.
  Reviewers may run any one campaign, any subset, or the full set, and each
  campaign should stand on its own without relying on prior campaign state.

Run the canonical VM-backed path:

```bash
bash run_vm_backed_campaign.sh 0.c0011
```

Keep the lab up for manual inspection:

`python3 scripts/run_lab_campaign.py --campaign 0.c0011 --keep-lab`

Use an explicit provider when needed:

`python3 scripts/run_lab_campaign.py --campaign 0.c0011 --provider qemu`

The orchestration does this in one path:

- `scripts/up_lab.sh`
- `apply_sut_profile.py`
- `scripts/run_campaign.py`
- `scripts/collect_evidence.sh`
- `scripts/generate_corpus_state.py`
- `scripts/destroy_lab.sh`

Operationally, `up_lab.sh` resolves the VM topology from the campaign's SUT
profile, starts the required provider-backed VMs, waits for core services, and
then applies the declared SUT profile automatically. That SUT application step
is where the lab receives campaign-specific weaknesses and prerequisites such as
weak users/passwords, writable directories, SUID binaries, and deliberately
vulnerable services like Apache. During execution, selected techniques may also
apply declared step-conditioned SUT overlays, such as exposing the Ray API
boundary immediately before `T1190` in `0.shadowray`. The follow-on execution
path then runs the campaign, collects evidence, refreshes corpus-state reports,
and tears the lab down unless `--keep-lab` is requested.

Important interpretation note:

- The repository derives a static SUT profile from a fixed corpus snapshot and
  then executes a declared campaign/SUT pair.
- Selected techniques may apply declared SUT overlays at runtime, but those
  overlays are explicit campaign metadata, not online CTI inference.
- The VM-backed path may bring up and health-check a Caldera node as part of
  the lab, but campaign execution is still driven by the STICKS runner rather
  than by the Caldera atomic planner used in `sticks-docker`.
- It does not act as an online planner that invents final commands or chooses
  vulnerabilities dynamically during execution.

The recommended representative VM-backed paths are:

- `bash run_vm_backed_campaign.sh 0.c0011` for the smallest end-to-end baseline;
- `bash run_vm_backed_campaign.sh 0.shadowray` when you want the same flow plus
  an explicit step-conditioned SUT overlay before `T1190`.

Use the direct Python entry point only when you need an explicit provider
override.

To inspect current campaign-by-campaign status before choosing a run:

```bash
cat results/CORPUS_STATE.md
cat results/CAMPAIGN_SUT_FIDELITY_MATRIX.md
```

For the most honest VM-backed read, prefer campaigns that are both:

- marked `Pair Valid = yes` in `results/CAMPAIGN_SUT_FIDELITY_MATRIX.md`;
- green in the latest evidence summary.

Development-only acceleration exists, but it is not the reviewer default:

```bash
python3 scripts/run_all_lab_campaigns.py --campaign 0.c0011 --campaign 0.c0015 --provider qemu --reuse-lab
```

```bash
python3 scripts/run_lab_campaign.py --campaign 0.c0015 --assume-lab-running
```

Use those only when you intentionally want to reuse a compatible running lab.
Reviewer-facing claims remain grounded in cold-start execution per campaign.

Exploratory helpers such as `multi_vm_manager_2vm.py` remain available for
infrastructure debugging, but they are not the reviewer-facing realism
contract.

## Current Expectations

- The smoke path is intended to be lightweight and reproducible.
- The published corpus is broader than strict pair validation, so use the
  matrix rather than filename presence alone when choosing a realism run.
- Live runs regenerate reviewer-visible evidence under `release/evidence/`.
- The public repository ships synthesized reports rather than heavyweight
  frozen evidence trees; this keeps the handoff portable without weakening the
  reproduction path.
- A clean checkout may therefore expose representative VM-backed evidence for
  only a subset of campaigns. The matrix and corpus-state reports make that
  explicit instead of implying that every campaign already has a shipped cold-start trace.
- On macOS ARM64 with `qemu`, the first cold-start can take materially longer
  than subsequent runs because guest bootstrap, package installation, and
  Caldera setup happen inside the VM. This is expected and should not be
  confused with hidden manual setup.

## Troubleshooting

If Python imports fail:

```bash
export PYTHONPATH="$PWD/src:$PYTHONPATH"
```

If you want to verify the local Caldera instance:

```bash
curl -s -H "KEY: ADMIN123" http://localhost:8888/api/v2/abilities | python3 -c "import json,sys; print(len(json.load(sys.stdin)))"
```

If the VM-backed path reports degraded state, use that output as an
infrastructure signal rather than assuming a campaign runner bug.
