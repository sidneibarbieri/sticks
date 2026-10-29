# STICKS VM-Backed Lab Environment

## Overview
This directory contains the provider-aware Vagrant substrate used by the
canonical STICKS VM-backed realism path.

Use this path through the canonical orchestration entry point:

```bash
python3 scripts/run_lab_campaign.py --campaign 0.c0011
```

That command resolves the campaign topology from `data/sut_profiles/<campaign>.yml`,
brings up only the required VMs, runs health checks, applies the SUT profile,
executes the campaign, refreshes evidence summaries, and tears the lab down
unless `--keep-lab` is requested.

## Topology Model

Typical VM roles:

- `caldera`
- `attacker`
- `target-linux-1`
- `target-linux-2`

The exact topology is campaign-specific and comes from the SUT profile.

### Execution mechanism

The current macOS ARM64 QEMU attacker role is an Ubuntu 22.04 VM with selected
tools, not Kali. The Caldera server is a separate VM. A running server and a
reachable attacker do not establish that a campaign used a Caldera operation
or originated from the attacker VM.

The C0026 legacy-parity path uses the STICKS Python runner and target-VM shell
executors. Its domain acquisition is simulated on the host. Its controlled
name resolution and benign payload transfer use loopback inside the target.
Collection, archiving, and chunking run inside the target. The controlled
chunks remain in the laboratory; this path does not demonstrate remote C2,
external exfiltration, or replay of the historical adversary procedure.
Inspect the per-technique execution mode and host in the run evidence before
interpreting a campaign summary. Caldera is still provisioned for this
topology, so its dependency acquisition can fail before any technique runs.
That infrastructure failure is distinct from a procedure failure.

For an isolated C0026 QEMU run, retain the lab until the independent target
probe runs inside `target-linux-1`. The completion command uploads the packaged
probe, executes it as root in that guest, records the observation, destroys
only the campaign's declared VMs, and seals the final evidence. It attempts
scoped teardown even if the probe fails. Run these commands from the artifact
root, using a new run directory outside the artifact:

```bash
python3 scripts/run_isolated_lab_campaign.py --campaign 0.c0026 --provider qemu --run-root /path/to/new-run --keep-lab
python3 scripts/complete_c0026_run.py --run-root /path/to/new-run
python3 scripts/finalize_isolated_lab_run.py --run-root /path/to/new-run --verify
```

The finalizer checks the original run manifests, the independent observation,
the runner summary, and the Vagrant state of every VM declared by the SUT
profile. It rejects changed evidence or a VM that remains running. Its receipt
binds the observation to the final evidence-tree digest. The C0026 contract
checks the target-chain observer. It does not certify historical fidelity or
external command and control.

C0010 has a separate observer and finalization contract. Start from a new run
directory and execute these commands from the artifact root:

```bash
python3 scripts/run_isolated_lab_campaign.py --campaign 0.c0010 --provider qemu --run-root /path/to/c0010-run --keep-lab
python3 scripts/complete_c0010_run.py --run-root /path/to/c0010-run
python3 scripts/finalize_isolated_lab_run.py --run-root /path/to/c0010-run --verify
```

`complete_c0010_run.py` invokes the observer, attempts teardown restricted to
C0010 even when observation fails, and seals only a successful cycle. If
teardown itself fails, inspect the run and retry the scoped cleanup; do not
claim completion. The C0010 receipt
checks the recorded implementation of each runner step, the packaged probe,
the guest transport result, five target checks, and all declared VM states.
The declared page and notice are SUT fixtures, not campaign-produced effects.
This contract establishes a bounded transfer record, not historical
watering-hole fidelity or external delivery.

ShadowRay has a separate fixture-observation contract. Start from a new run
directory and execute these commands from the artifact root:

```bash
python3 scripts/run_isolated_lab_campaign.py --campaign 0.shadowray --provider qemu --run-root /path/to/shadowray-run --keep-lab
python3 scripts/complete_shadowray_run.py --run-root /path/to/shadowray-run
python3 scripts/finalize_isolated_lab_run.py --run-root /path/to/shadowray-run --verify
```

Completion records the guest-only probe transport, attempts campaign-scoped
teardown even when observation fails, and seals only a passing bounded cycle.
The receipt checks the version-bound probe and campaign contract, all four
fixture observations, simulation-scoped products, and declared VM states.
It does not certify privilege escalation, shell-startup persistence, historical
fidelity, executor identity, or cross-host ingress. A successful runner row
alone is not an observed guest effect.

CostaRicto has a bounded guest-file and service contract. From the artifact
root, use a new run directory outside the checkout:

```bash
python3 scripts/run_isolated_lab_campaign.py --campaign 0.costaricto --provider qemu --run-root /path/to/costaricto-run --keep-lab
python3 scripts/complete_costaricto_run.py --run-root /path/to/costaricto-run
python3 scripts/finalize_isolated_lab_run.py --run-root /path/to/costaricto-run --verify
```

Completion runs the packaged read-only guest probe, attempts scoped teardown
even if observation fails, and seals only a passing cycle. The receipt binds
the source, runner rows, raw guest transport, fixture checks, and final VM
states. It distinguishes three controlled lab steps from seven simulated
steps. File staging does not prove external tool acquisition; the benign
fixtures do not demonstrate a historical intrusion or complete campaign
effects.

## Setup

### Prerequisites
- Vagrant 2.4+
- Linux x86_64: `libvirt` + `vagrant-libvirt`
- macOS ARM64: QEMU + `vagrant-qemu`

### Quick Start
```bash
python3 scripts/run_lab_campaign.py --campaign 0.c0011
```

By default, the `caldera` role installs only the Caldera core needed by the
canonical STICKS path. Optional Docker support is intentionally disabled to
reduce cold-start cost on ARM64/QEMU. Enable it only when you explicitly need
it:

```bash
STICKS_CALDERA_INSTALL_DOCKER=1 python3 scripts/run_lab_campaign.py --campaign 0.c0011 --provider qemu
```

The Atomic Red Team plugin and its large upstream data checkout are also
disabled by default. The eight retained campaigns use their versioned
executors, not this plugin. Enable the pinned Atomic input checkout only for
an experiment that explicitly requires that plugin:

```bash
STICKS_CALDERA_WITH_ATOMIC=1 python3 scripts/run_lab_campaign.py --campaign 0.c0011 --provider qemu
```

An optional-plugin run has a different SUT configuration and must be reported
as such; it does not retroactively qualify the default configuration.

The default `caldera` path also skips the optional build toolchain and installs
only the canonical runtime dependency slice needed by the enabled plugin set.
That slice is versioned in `shared/caldera-runtime-requirements.txt` instead of
being inferred ad hoc during provisioning. If your host needs compiled wheels
for Caldera dependencies, opt back into the heavier toolchain explicitly:

```bash
STICKS_CALDERA_INSTALL_BUILD_DEPS=1 python3 scripts/run_lab_campaign.py --campaign 0.c0011 --provider qemu
```

The `attacker` role follows the same pattern. Core tooling needed by the
current canonical path stays enabled by default, while heavier reconnaissance
and cracking packages are opt-in:

```bash
STICKS_ATTACKER_INSTALL_EXTENDED_TOOLS=1 python3 scripts/run_lab_campaign.py --campaign 0.c0011 --provider qemu
```

The shared `base` role now stays intentionally minimal. Role-specific packages
such as `git`, `pip`, `sshpass`, and extended reconnaissance tooling are
installed only where the canonical path actually needs them.

### Development Acceleration
On macOS ARM64 with `vagrant-qemu`, the current provider path does not expose
Vagrant snapshot support. The supported acceleration path is therefore warm-lab
reuse, not snapshot rollback.

Use these flags only for development and corpus expansion:

```bash
python3 scripts/run_all_lab_campaigns.py \
  --campaign 0.c0011 \
  --campaign 0.c0015 \
  --provider qemu \
  --reuse-lab
```

The batch summary and each campaign's prospective evidence are written under
the ignored `runs/lab-batches/` directory by default. An explicit `--output`
must point outside the frozen `release/` and `results/` trees. Reuse mode
retains a shared lab state between campaigns and must not be treated as an
independent cold-start reproduction.

If a compatible lab is already running, the first startup step can also be
skipped explicitly:

```bash
python3 scripts/run_lab_campaign.py --campaign 0.c0015 --assume-lab-running
```

The canonical public-facing path remains a clean cold-start run without these
flags.

### Manual Setup
```bash
./scripts/up_lab.sh --campaign 0.c0011 --provider qemu
python3 scripts/run_campaign.py --campaign 0.c0011
./scripts/collect_evidence.sh
python3 scripts/generate_corpus_state.py
./scripts/destroy_lab.sh --campaign 0.c0011
```

## VM Access

### Target VM
```bash
cd target-linux-1
vagrant ssh
```

### Attacker VM
```bash
cd attacker
vagrant ssh
```

Provider-specific networking differs. On macOS ARM64 with `qemu`, forwarded
ports may be more reliable than private-network declarations. The canonical
health gate is `lab/health_check.py`, not ad hoc assumptions about host access.

## Cleanup
```bash
./scripts/destroy_lab.sh --campaign 0.c0011
```

## Troubleshooting

### Provider Detection
```bash
./scripts/up_lab.sh --campaign 0.c0011
```

Defaults:

- Linux x86_64 → `libvirt`
- macOS ARM64 → `qemu`

### Vagrant Issues
```bash
vagrant status
```

### Health Check
```bash
python3 lab/health_check.py --campaign 0.c0011 --provider qemu --output release/evidence
```
