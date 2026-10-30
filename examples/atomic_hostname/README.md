# One external procedure, with an explicit laboratory contract

This example qualifies Atomic Red Team's **Hostname Discovery** (`T1082`, GUID
`486e88ea-4f56-470f-9b57-3f4d73f39133`). Its upstream YAML, license, revision and
SHA-256 are retained here. The executed upstream command is unchanged: `hostname`.
Only that selected command is executable through this example; other tests in the
retained YAML are source material, not commands the runner will execute.

STICKS supplies a new, explicitly authored template, target binding, shell
precondition and observable-result predicate. The existing finite-domain pipeline
admits the template against that binding catalog. The source plan is an external
qualification fixture, **not** a campaign compiled from STIX. This is a concrete
integration example, not an automatic importer for arbitrary Atomic Red Team tests.

The existing frozen action catalog is unchanged. No corpus-wide coverage increase
is claimed. The template is outside that catalog until separately qualified for
the intended campaign and SUT.

## Run

Use the artifact's pinned Python environment and a running Docker engine. The
manifest pins a Linux ARM64 image digest, locally qualified with Docker on Colima;
no compatibility with another architecture is claimed. Install that exact image
before the run if absent. The runner uses `--pull=never` and does not download
dependencies during execution.

From the artifact root:

```sh
.venv/bin/python examples/atomic_hostname/qualify.py --output-dir runs/atomic-hostname-001
.venv/bin/python examples/atomic_hostname/qualify.py --output-dir runs/atomic-hostname-001 --verify-only
```

To inspect the retained qualification without Docker:

```sh
.venv/bin/python examples/atomic_hostname/qualify.py --output-dir examples/atomic_hostname/qualified --verify-only
```

The output directory must be new for an execution. Verification is offline and
requires the exact qualification source retained with the receipt.

Each of three cells gets a fresh target: network disabled, read-only root filesystem,
non-root UID/GID, all capabilities dropped, no privilege escalation, and explicit
CPU, memory, process and lifetime limits. The target is removed and its absence
checked before the next cell. Existing containers are not changed.

| Cell | Command return code | Expected observation |
| --- | --- | --- |
| Unchanged upstream command | 0 | Hostname matches independently read target identity |
| Wrong-output control | 0 | Rejected: another hostname |
| Empty-output control | 0 | Rejected: no hostname |

The controls intentionally substitute the executed command; their receipts record
that difference. They are not admitted alternatives to the upstream procedure.
The observer reads `/etc/hostname` in a separate invocation and checks it against
Docker's configured identity, rather than treating command completion as discovery.

## What the receipt establishes

The JSON records retain the external source, authored contract, source plan,
binding catalog, admitted plan, exact command, image identity, output, predicate
decision and cleanup result. Offline verification recomputes admission and each
output predicate and rejects missing cells, reused targets and altered contracts.
It does not reexecute Docker or independently prove a historical cleanup event.

This qualifies one read-only discovery procedure and its negative controls. It
does not establish historical fidelity, an enterprise pivot, a complete campaign,
detection quality, or generic external-library compatibility. Receipts assume a
trusted controller directory; hashes are integrity checks, not signatures.
