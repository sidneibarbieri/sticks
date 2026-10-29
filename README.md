# STICKS Public Artifact

STICKS is a finite-domain procedural-admission artifact. It compiles pinned
ATT&CK campaign structure into typed plans, enumerates candidates from a
versioned template catalog, checks them against an explicitly scoped state,
and records what the CTI, environment, and reconstruction each contribute.

## Repository structure

- `src/`: compiler, contracts, finite-domain concretization, and evaluation.
- `data/`: pinned STIX input and versioned procedure-template catalog.
- `release/`: plans, experiment records, claim ledger, and evidence hashes.
- `docs/`: reconstruction, realization-space, and state-fact semantics.
- `tests/`: executable checks linked from the claim ledger.

## Evaluation qualities

This release is prepared for availability, functionality, sustainability,
and experiment-reproducibility review. Availability also depends on the
distribution channel providing this package through a stable public URL.

## Basic information

The primary path requires a POSIX-like shell, Python 3.11 or later, `venv`,
and `pip`. The reference dependency lock targets Python 3.11.15. No GPU is
needed. A machine with two CPU cores, 4 GiB of RAM, and 1 GiB of free disk is
sufficient for the primary gate; allow five minutes after dependencies are
installed. Runtime varies by host.

## Dependencies

`requirements.lock` records every direct and transitive Python dependency at
an exact version. `requirements.txt` installs that lock without resolving an
unpinned package set. The pinned ATT&CK input and template catalog ship in the
repository, so the experiment path does not fetch data at runtime.

## Security considerations

The primary reviewer path performs deterministic local computation and one
benign loopback transfer. It requires no credentials, external service,
container runtime, hypervisor, or model API. The secondary legacy path can
manage virtual machines and adversary-emulation infrastructure; run it only
in an isolated disposable laboratory. It is not needed for registered claims.

## Installation

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Minimal test

```bash
.venv/bin/python -m pytest tests/test_realization_space.py -q -p no:cacheprovider
```

Expected result: every realization-space test passes and the process exits
with status zero.

## Optional QA dependencies

The primary lock does not include the legacy HTTP client. To exercise the
mocked legacy infrastructure paths, create a separate QA environment:

```bash
python3 -m venv .venv-qa
.venv-qa/bin/python -m pip install -r requirements-qa.txt
.venv-qa/bin/python -m pip check
.venv-qa/bin/python -m pytest tests/test_legacy_infrastructure_paths.py -q -p no:cacheprovider
```

This exact optional Python profile extends, rather than replaces, the
primary lock. These tests mock provider calls: passing is not VM campaign
qualification. Installation needs package-index access; the tests do not.

`tests/test_qemu_network_serialization.py` requires Ruby with its YAML
standard library. `tests/test_workbench_browser_state.py` requires Node.js
on PATH for its JavaScript state test. Without those interpreters the
corresponding tests explicitly skip. To check them when available:

```bash
ruby -ryaml -e 'puts RUBY_VERSION'
node --version
.venv-qa/bin/python -m pytest tests/test_qemu_network_serialization.py tests/test_workbench_browser_state.py -q -p no:cacheprovider
```

These checks do not boot a VM or measure campaign effects. Tests requiring
real lab-run evidence can still skip when that evidence is absent. Report
executed and skipped tests separately; installing QA dependencies does
not supply missing execution evidence.

To select an existing environment for the complete reviewer wrapper:

```bash
STICKS_PYTHON="$PWD/.venv-qa/bin/python" bash run_review_check.sh
```

`STICKS_PYTHON` overrides the repository `.venv` and PATH. It must name an
executable interpreter with core dependencies. An invalid selection fails
without installation or fallback. Without it, the wrapper retains the
repository `.venv`, then PATH selection. Install the chosen profile before
running the wrapper; this selector does not verify exact dependency pins.

## Experiments

### Inspect admission in the graphical workbench

```bash
.venv/bin/python scripts/run_realization_workbench.py --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/` to inspect the pinned campaign inventory and
bounded candidate admission. This is a planning interface, not campaign
execution evidence. Stop the server with Ctrl-C. See
`docs/reviewer_quickstart.md` for scope and the canonical validation path.

### Reproduce the registered evidence

The following command reproduces every non-blocked registered property:

```bash
bash run_review_check.sh
```

After dependency installation, this command is offline. It regenerates the
evidence, validates SHA-256 hashes, audits claim chains, checks the public
surface and complete public-tree manifest, and runs the tests. It needs no
Docker, VM, API key, or paid model.

Expected headline output includes 55 campaigns and
1146 steps in the corpus, 252 catalog-supported
steps, 0/25 admitted steps from the unaugmented
representation versus 25/25 reconstructed steps
in the deep slice, 54 binding occurrences, and
79 explicit execution commitments.

### Corpus coverage and deep admission

`bash run_review_check.sh` recompiles all released Enterprise campaigns and
regenerates the corpus-coverage and three-campaign deep-slice records. Inspect
`release/experiments/` and `release/claims/verification.json`. Expected result:
all non-blocked ledger properties verify; limited and blocked properties remain
visibly qualified rather than being promoted.

### Bounded realization-space example

```bash
.venv/bin/python scripts/enumerate_realization_space.py           --plan release/plans/C0010.procedural-plan.json           --bindings release/plans/C0010.binding-catalog.json           --templates data/concretization/action_templates.json           --maximum-realizations 64           --maximum-search-states 20000           --output /tmp/C0010.realization-space.json           --require-realization
```

Expected result: a bounded, hash-valid space with 64 serialized schedule
graphs, one causal structure, and operational status `not_run`. This command
enumerates candidates; it does not claim that they were executed.

### State-fact semantic audit

```bash
.venv/bin/python scripts/audit_fact_semantics.py           --output /tmp/fact-semantics-audit.json
```

Expected result: all three frozen deep-slice SUT catalogs are conformant.
The check verifies versioned fact identity and permitted origins only; it
does not establish a live state or operational effect. See
`docs/FACT_SEMANTICS.md` for the contract and non-claims.

## Evidence map

- `release/claims/ledger.json`: registered and blocked properties.
- `release/claims/evidence_sha256.json`: frozen integrity manifest.
- `release/experiments/`: generated experiment records and tables.
- `release/plans/`: typed plans, catalogs, and concretized plans.
- `release/paper_macros.tex`: generated manuscript values.
- `PUBLIC_TREE_SHA256.json`: hash and size of every shipped file.
- `tests/`: checks linked from the ledger.

When a manuscript source is colocated with the artifact, audit it too:

```bash
PAPER_DIR=../paper bash run_review_check.sh
```

## Interpretation boundary

The catalog supports 252 of 1146 corpus steps
(22.0%). The deep evaluation
covers three fully supported campaigns and demonstrates the admission
mechanism, not corpus-wide replay coverage. The artifact does not claim
historical reconstruction, full campaign replay, observational equivalence,
or analyst-effort reduction.

## Secondary legacy experiments

Earlier container, VM, and SUT experiments remain available for inspection and
compatibility. They are outside the primary claim ledger:

```bash
bash run_review_check.sh --legacy
```

A green legacy check does not support a property absent from the ledger.
For a new VM-backed campaign with isolated source, raw artifacts, and
evidence, use `scripts/run_isolated_lab_campaign.py`. Platform setup,
the pinned Node cache option, and interpretation limits are in
`docs/IAC_LIMITATIONS_ARM64.md`. This path requires a hypervisor and
network access, unlike the offline primary gate.

For a retained QEMU Linux run, `scripts/observe_controlled_target.py`
checks declared fixtures, a benign loopback transfer, and the preserved
browser-discovery report without importing the executors. The command,
explicit scope, failure behavior, and teardown requirement are documented
in `docs/IAC_LIMITATIONS_ARM64.md`. This does not qualify unrelated
techniques or historical fidelity.

The C0026 target-chain profile has a separate completion command:
`scripts/complete_c0026_run.py --run-root PATH`. It uploads and runs
the packaged target probe, attempts campaign-scoped teardown even when
observation fails, and seals the final receipt only after success.
See `lab/vagrant/README.md` for the complete command sequence.

For two sealed QEMU runs created from the same source tree, retain both
run directories and audit their typed outcomes with:

```bash
PYTHONPATH=src:. python3 -m scripts.audit_typed_campaign_outcomes \
  --run-root /path/to/C0010-run --run-root /path/to/C0026-run
```

The auditor recomputes each final receipt and reports observed effects
on the target and controller separately from simulations and failures.
It checks the recorded VM teardown states against the required VM names
without invoking Vagrant; it cannot re-observe the historical teardown.
It rejects different source trees. The default offline package contains no
QEMU run directories; this command validates new or separately
supplied runs. Passing the offline review check alone does not
establish VM-backed campaign execution.

If a separately supplied typed-evidence archive accompanies this
repository, verify it from the package root with:

```bash
PYTHONPATH=src:. python3 -m scripts.verify_typed_evidence_archive \
  --archive /path/to/typed-qemu-evidence.tar.gz
```

This command rejects archive links, unsafe paths, AppleDouble files,
and oversized members before extracting into a temporary directory.
It then verifies both sealed receipts using their recorded VM states.
When `--typed-evidence-archive` is supplied, the package includes
`typed-run-evidence/c0010-c0026.tar.gz`, binds its bytes in
`PUBLIC_TREE_SHA256.json`, and verifies it during `run_review_check.sh`.
This checks recorded outcomes, not a new VM execution or publication safety.
No QEMU result should be inferred when the archive is absent.

## License

STICKS-authored material is released under the MIT License; see
`LICENSE`. Pinned third-party inputs have separate terms recorded in
`THIRD_PARTY_NOTICES.md`.

## Private typed-run evidence candidate

`typed-run-evidence/c0010-c0026.tar.gz` is included in the tree manifest and audited by `run_review_check.sh`. The check screens changed bytes for recognizable identifiers and secrets, and reports reference-fixture matches separately. This selected archive is a private release candidate pending content and privacy approval. The audit replays sealed receipts and recorded VM states; it does not rerun QEMU or certify historical fidelity. Receipt source hashes identify the archived run source, before the evidence archive and release metadata were added to this package.
The privacy screen compares this archive with the bundled reference manifest byte-identical to both sealed run workspaces. The receipts and source manifests are independently verified. Lexical screening does not replace semantic privacy approval.

## C0045 compute-effect series (anonymous review)

`release/experiments/c0045_compute_effect_series/series.tar.gz` is bound by `PUBLIC_TREE_SHA256.json` and replayed by `bash run_review_check.sh`. To replay only its 20 selected cells, run `PYTHONPATH=src:. python3 -m scripts.verify_c0045_effect_series_archive --archive release/experiments/c0045_compute_effect_series/series.tar.gz`. The replay checks recorded target CPU effects and three controls per block; it does not execute a new QEMU campaign or establish historical ShadowRay fidelity. The hash-bound semantic review approves this archive for anonymous review only. Identified release requires separate approval.
