# IaC Limitations - macOS ARM64 (Apple Silicon)

## Context

The STICKS artifact uses Vagrant with multiple virtualization backends to provision the lab infrastructure. On macOS ARM64 (Apple Silicon), the available backends differ significantly from x86_64 Linux, which impacts network configuration, performance, and experimental validity.

## Provider Comparison

| Feature | VirtualBox | QEMU (vagrant-qemu) | Libvirt |
|---|---|---|---|
| **macOS ARM64 support** | No (x86_64 only) | Yes | Partial (requires libvirt daemon) |
| **Private network** | Full support | Explicit backend required | Requires session URI |
| **Port forwarding** | Full support | Supported | Supported |
| **Performance** | Native x86 | Emulated ARM64 | Near-native (when available) |
| **Vagrant plugin** | Built-in | `vagrant-qemu` | `vagrant-libvirt` |
| **Artifact recommendation** | x86_64 hosts only | macOS ARM64 default | Linux hosts |

## Critical Issue: QEMU Needs an Explicit Private-Network Backend

The `vagrant-qemu` provider ignores `private_network` unless the Vagrantfile
enables its advanced-network mode. The multi-host lab selects `socket_vmnet`,
which provides a shared host-and-VM subnet while Vagrant runs unprivileged.

The QEMU Vagrantfiles load `shared/qemu_network_yaml.rb` to preserve MAC strings
across the provider's Ruby serializer and the guest's cloud-init YAML parser.
Without this compatibility layer, numeric-only MACs such as
`52:54:00:35:54:10` can be interpreted as numbers, leaving both NICs down.
The layer emits the same network document as JSON, a YAML-compatible format.
It does not modify the globally installed provider or repair a running guest.

### Impact

- **A local daemon is required**: `socket_vmnet` owns the privileged network capability.
- **The daemon subnet is part of the experiment**: it must contain the declared
  lab addresses (`192.168.56.0/24`) and be recorded with the run receipt.
- **Connectivity must be measured**: successful boots do not establish the
  declared attacker-to-target topology.

### Mitigation

1. **Install and configure the local backend once**:

   ```bash
   brew install socket_vmnet
   vmnet_binary="$(brew --prefix socket_vmnet)/bin/socket_vmnet"
   test -x "$vmnet_binary"
   sudo "$vmnet_binary" --vmnet-gateway=192.168.56.1 --vmnet-dhcp-end=192.168.56.9 \
     /opt/homebrew/var/run/socket_vmnet
   ```

   Keep that daemon running during the campaign. Do not run Vagrant as root.
   Homebrew may install this root-only helper without linking it into its global
   `bin` directory. Resolve its formula prefix instead of assuming
   `/opt/homebrew/bin/socket_vmnet`. Enter the administrator password only at
   the local sudo prompt. An existing socket file does not prove the daemon is live.

2. **SSH port forwarding**: Each VM has a unique forwarded SSH port on `127.0.0.1`:
   - caldera: `2201`
   - attacker: `2202`
   - target-linux-1: `2203`
   - target-linux-2: `2204`

   The Vagrantfiles disable Vagrant's duplicate SSH forwarding rule while
   retaining the QEMU provider's own host-to-guest SSH mapping. Automatic
   correction is disabled because it previously assigned the same fallback
   port to multiple guests.

3. **Health check fallback**: `lab/health_check.py` tries private IP first, then falls back to forwarded ports for QEMU provider.

4. **Service access**: Caldera API (`8888`) is reached at
   `192.168.56.10:8888` from the host and the other VMs. The lab does not
   forward this port through QEMU user-mode networking.

## Read-only Controlled-Target Observation

Retain an isolated run with `--keep-lab` to observe the guest before teardown.
From the packaged artifact, run:

```bash
.venv/bin/python scripts/observe_controlled_target.py \
  --workspace /path/to/run/workspace \
  --campaign 0.outer_space \
  --browser-report data/artifacts/0.outer_space_browser_discovery.txt \
  --output /path/to/run/target-observation.json
```

The QEMU observer reads the declared fixtures through guest SSH, compares their
complete path set, hashes, owners, permissions, and owner readability, and checks
the benign T1105 loopback payload against the guest HTTP log. It compares the
preserved T1217 report with the declared browser owner and paths. This report
comparison is not independent measurement of the executor process identity.
The probe also checks that at least two network MAC addresses remain strings.
Only fixture paths and owners are sent to the probe, not declared file contents.

The output binds the profile, browser report, CLI, validator, and probe by hash.
Hashes identify the input bytes captured before the guest query. If an input
changes during that query, the transport receipt records the changed input and
the observer fails without issuing a successful observation.
A separate transport receipt preserves stdout and stderr even if schema
validation fails. Receipts cannot overwrite earlier observations. Missing
fixtures, malformed observations, and failed SSH exit with an error; no host
filesystem fallback is used. The probe writes no guest files, although SSH and
sudo may create normal system audit entries.

This observer covers the stated controlled Linux fixtures and two bounded
effects. It does not validate unrelated simulated steps, historical fidelity,
cross-machine ingress, Windows, or other providers. Destroy the retained lab
explicitly after observation using the run's documented teardown command.

## Retained ShadowRay Fixtures

From the isolated run's `workspace/lab/vagrant/target-linux-1` directory, the
guest-only probe can be run without installing it in the guest:

```bash
vagrant ssh -c 'python3 -' < /path/to/artifact/scripts/probe_shadowray_target.py
```

Preserve stdout, stderr, the exit code, and the probe's SHA-256 in a new receipt.
The probe compares the downloaded file with its retained source and the backup
with its shell fixture, checks the recorded HTTP request, and observes toolkit
file permissions. Missing files and symlinks fail rather than using host data.
It does not reexecute the techniques or prove privilege escalation, historical
fidelity, shell-startup activation, process identity, or cross-host ingress.

The ShadowRay SUT can deliberately mark Bash setuid. The isolated shell-startup
fixture therefore uses `setpriv --no-new-privs` so Bash can load its custom rcfile
without gaining new privileges. The lab requires Linux `setpriv` from util-linux.
This does not remove the SUT weakness or qualify the inspired T1068 simulation.

## Caldera on ARM64

- Caldera 5.x uses **SQLite by default** - MongoDB is NOT required.
- Previous provisioning scripts attempted to start `mongodb.service`/`mongod.service`, which don't exist on Ubuntu 22.04 ARM64 without explicit MongoDB installation.
- The provisioner pins Caldera 5.3.0 to a checked commit, initializes the
  selected plugin submodules, installs Go 1.22, builds the Magma frontend with
  Node 22.22.3, and requires a successful HTTP response on port 8888.
- Atomic Red Team inputs are fetched before service startup and checked against
  commit `388942adbd9641f4dfdcf079d7efe9a75ec0ac43`. The fetch is limited to
  600 seconds. A mismatched checkout or missing STIX input fails provisioning
  rather than allowing an unpinned download during the plugin's startup hook.
- The Node archive is verified against a pinned SHA-256 for ARM64 or x86_64.
  By default it is downloaded inside the guest. A previously downloaded
  archive can be reused by setting `STICKS_NODE_ARCHIVE` to its host path
  before `up_lab.sh`; the same guest-side hash check still applies. This
  option reduces repeat setup time but is not required for reproduction.
- The QEMU preflight connects to the configured socket, rather than accepting
  a stale socket file. All VM definitions use `STICKS_SOCKET_VMNET_SOCKET`
  when set. The daemon must provide the declared `192.168.56.0/24` subnet;
  guest-local HTTP readiness does not establish host or inter-VM connectivity.

## Experimental Validity Considerations

The virtualization backend **influences experimental validity**:

1. **Network topology fidelity**: If the provider ignores private networks, the declared topology (attacker → target connectivity) may not reflect actual state. This must be measured, not assumed.

2. **Architecture emulation**: ARM64 guests on ARM64 host run natively. x86_64 guests would require full emulation, significantly impacting performance and potentially behavior.

3. **Evidence must record backend**: The health check report and campaign evidence include provider information so reviewers can assess infrastructure constraints.

## Recommendations for Artifact Reviewers

| Reviewer Host | Recommended Provider | Notes |
|---|---|---|
| Linux x86_64 | libvirt or VirtualBox | Full private network support |
| macOS x86_64 | VirtualBox | Full private network support |
| macOS ARM64 | QEMU + socket_vmnet | Record daemon subnet and health report |

For maximum reproducibility on macOS ARM64:

1. Install QEMU and the validated `vagrant-qemu` 0.6.3 provider. The older
   0.3.12 provider silently ignores the advanced private-network settings; a
   newer provider is not accepted until its transport behavior is qualified.
2. Install and start `socket_vmnet` for `192.168.56.0/24` as shown above.

3. Before a strict multi-host run, apply and verify the provider transport
   repair. `socket_vmnet` uses its client wrapper and QEMU file descriptor 3;
   a generic QEMU `stream` capability does not prove protocol compatibility:

   ```bash
   python3 scripts/apply_vagrant_qemu_socket_vmnet_fix.py
   python3 scripts/apply_vagrant_qemu_socket_vmnet_fix.py --check
   ```

   `up_lab.sh` independently inspects the running QEMU commands and fails if
   any requested VM uses `-netdev stream` rather than the fd route.
4. Run `./up_lab.sh --campaign <ID>` with an isolated evidence directory.
5. Review the health report before accepting a campaign receipt.

For a new campaign, prefer an independent workspace and evidence root:

```bash
python3 scripts/run_isolated_lab_campaign.py \
  --campaign 0.c0011 --provider qemu \
  --run-root /absolute/path/to/a/new-run-directory \
  --node-archive /absolute/path/to/node-v22.22.3-linux-arm64.tar.xz
```

The run directory must not exist yet. `--node-archive` is optional; without it,
the guest downloads the pinned release. The guest verifies its SHA-256 in
either case. The command writes `run_context.json`, source and output SHA-256
manifests, raw `workspace/data/artifacts`, and an `evidence` directory. A
failed run retains these records and returns a nonzero exit code. Inspect
`summary.json` per step: VM health, executor success, fidelity, and observed
effects are different claims. Do not merge these prospective results into
the frozen release or paper metrics without a separate audit.

For the bounded typed C0010 laboratory path, run from a fresh reviewer
package after its deterministic checks pass:

```bash
python3 scripts/run_isolated_lab_campaign.py \
  --campaign 0.c0010 --provider qemu --keep-lab \
  --run-root /absolute/path/to/a/new-c0010-run
python3 scripts/complete_c0010_run.py \
  --run-root /absolute/path/to/a/new-c0010-run
python3 scripts/finalize_isolated_lab_run.py \
  --run-root /absolute/path/to/a/new-c0010-run --verify
```

The completion command records the independent target observation while the
guest is running, destroys the three declared VMs, and seals the receipt.
Without `--keep-lab`, the guest is destroyed before that observation and the
finalizer rejects the run. Its receipt distinguishes four controller effects,
one bounded guest transfer, and four simulations. It does not certify a
historical watering-hole intrusion or five effects in the guest. Provisioning
still downloads pinned Caldera sources and guest dependencies unless a
separately validated offline cache is supplied.

For the bounded typed C0026 path, retain the laboratory until the independent
guest observations are complete:

```bash
python3 scripts/run_isolated_lab_campaign.py \
  --campaign 0.c0026 --provider qemu --keep-lab \
  --run-root /absolute/path/to/a/new-c0026-run
python3 scripts/complete_c0026_run.py \
  --run-root /absolute/path/to/a/new-c0026-run
python3 scripts/finalize_isolated_lab_run.py \
  --run-root /absolute/path/to/a/new-c0026-run --verify
```

The completion script observes the live target, tears down the three declared
VMs, and seals the receipt. A successful campaign runner invocation without
`--keep-lab` does not qualify C0026: the target is gone before the independent
observation can run. Preserve failed run directories for diagnosis; start any
retry in a new directory.

## Related Files

- `lab/health_check.py` - 3-level health check with provider-aware fallback
- `lab/vagrant/shared/caldera.sh` - Fail-fast Caldera provisioning (no MongoDB)
- `lab/vagrant/shared/base.sh` - Fail-fast base provisioning
- `lab/vagrant/*/Vagrantfile` - Provider blocks for libvirt, virtualbox, qemu
- `up_lab.sh` - Provider auto-detection and health check integration
- `setup.sh` - Dependency installation including QEMU for ARM64
