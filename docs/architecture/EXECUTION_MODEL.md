# Execution Model

This document records the verified execution architecture of `sticks/` and the
target direction for its next cleanup and stabilization steps.

## Verified current state

### 1. Canonical reviewer path

The only reviewer-facing execution contract currently grounded in code and
documentation is:

```bash
./artifact/setup.sh
./artifact/run.sh
./artifact/validate.sh
```

This path resolves to:

- `scripts/run_campaign.py`
- `src/runners/campaign_runner.py`
- `src/loaders/campaign_loader.py`
- `src/executors/registry_initializer.py`

It executes directly on the host and does not provision VMs.

### 2. Optional lab path

The provider-aware optional lab path is centered on:

- `scripts/up_lab.sh`
- `src/apply_sut_profile.py`
- `lab/health_check.py`
- `scripts/destroy_lab.sh`
- `lab/vagrant/`

This path resolves VM topology from the SUT profile and is the best current
foundation for a future full-lab execution contract.

The current VM-backed path now has two explicit SUT layers:

- a base SUT profile applied once during lab bring-up; and
- optional step-conditioned SUT overlays applied immediately before selected
  techniques.

### 3. QEMU-specific helpers

Two direct QEMU managers coexist:

- `multi_vm_manager_2vm.py`: attacker + target VMs, Caldera on the host
- `multi_vm_manager.py`: older 3-VM exploratory setup with Caldera inside a VM

These helpers are useful for diagnostics and host-specific experimentation, but
they are not the same thing as the provider-aware optional lab contract.

### 4. Paper 2 measurement path

The current Paper 2 chain is:

1. `measurement/sut/scripts/sut_measurement_pipeline.py`
2. `measurement/sut/scripts/results/todo_values_latex.tex`
3. `scripts/sync_manuscript_values.py`
4. `../ACM CCS - Paper 2/results/values.tex`

This chain is now measurement-backed for the current macro surface.

## Architectural conflicts that remain

- There is no single optional-lab entry point that covers topology resolution,
  provisioning, weakness application, health gates, execution, evidence, and
  teardown in one command.
- The direct QEMU helpers and the provider-aware Vagrant path encode different
  control-plane assumptions for Caldera.
- Non-canonical root-level wrappers such as `campaign_pipeline.py` and
  `evidence_collector.py` contain exploratory orchestration logic that is not
  aligned with the canonical runner contract.
- Some historical outputs and documents still reference
  `unified_campaign_runner.py`, which is no longer the current entry point.

## Target architecture

### Control plane

The project should converge on one optional-lab control plane:

- SUT profile decides required roles and host count.
- Provider selection remains automatic and host-aware.
- `qemu` remains the practical macOS ARM64 substrate.
- `libvirt` remains the preferred Linux substrate.
- Vagrant stays as the lifecycle layer when the lab path is used.

Direct QEMU managers should remain diagnostic helpers unless and until they are
folded into the same contract.

### Role model

The lab should be modeled around explicit roles:

- `caldera-base`
- `attacker-base`
- `linux-target-base`
- future `windows-target-base`

### Capability overlays

Target hosts should be composed from a minimal base plus capability overlays,
not from monolithic preloaded images.

Current recommended overlay taxonomy:

- `web-profile`
- `db-profile`
- `app-profile`
- `fileshare-profile`

Campaign-specific weaknesses, package versions, and service exposure should be
applied by SUT profile and provisioning logic, not hidden inside a single
bloated image. When a precondition matters only for one technique, it should be
expressed as a step-conditioned overlay rather than baked into the base image.

## Required health gates

The optional lab path should enforce three distinct gates:

1. `infra_ready`: VMs exist and SSH is reachable
2. `service_ready`: required services respond, especially Caldera API when used
3. `campaign_ready`: topology-specific flows are validated for the active SUT

Campaign execution should not be reported as equivalent to a healthy multi-host
run when the control plane required by that campaign is not ready.

## Near-term cleanup priorities

1. Keep the reviewer path stable and separate from lab-only claims.
2. Remove stale references to `unified_campaign_runner.py`.
3. Collapse duplicate optional-lab entry points toward one provider-aware flow.
4. Move root-level exploratory wrappers out of the reviewer-facing mental path.
5. Revalidate multi-host execution only after the health gates above are
   enforced by code, not by documentation alone.
