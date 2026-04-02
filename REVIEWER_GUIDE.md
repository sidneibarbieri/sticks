# Reviewer Guide

This guide keeps the reviewer path short and explicit.

## Recommended Order

1. Run the canonical smoke path.
2. Validate that evidence and tables were created.
3. If you want the realistic VM-backed substrate, run the canonical lab path.

## 1. Smoke Path

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

## 2. Direct Commands

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

## 3. VM-Backed Realism Path

The repository also contains a provider-aware VM-backed path for realism
checks. This path is not required for the smoke path, but it is the supported
way to validate the QEMU/libvirt-backed substrate.

Important:

- The smoke path does not depend on QEMU or Caldera being green.
- The smoke path does not require a specific host platform or hypervisor.
- The preferred VM-backed backend is `libvirt` on Linux and `qemu` on macOS ARM64.
- VM-backed claims should be based on a fresh run of the canonical lab path in
  the same checkout.
- The VM-backed unit of validation is a single self-contained campaign/SUT pair.
  Reviewers may run any one campaign, any subset, or the full set, and each
  campaign should stand on its own without relying on prior campaign state.

Run the canonical VM-backed path:

```bash
python3 scripts/run_lab_campaign.py --campaign 0.c0011
```

Keep the lab up for manual inspection:

```bash
python3 scripts/run_lab_campaign.py --campaign 0.c0011 --keep-lab
```

Use an explicit provider when needed:

```bash
python3 scripts/run_lab_campaign.py --campaign 0.c0011 --provider qemu
```

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
vulnerable services like Apache or the Ray dashboard. The follow-on execution
path then runs the campaign, collects evidence, refreshes corpus-state reports,
and tears the lab down unless `--keep-lab` is requested.

The recommended representative VM-backed path is currently:

```bash
python3 scripts/run_lab_campaign.py --campaign 0.c0011 --provider qemu
```

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
