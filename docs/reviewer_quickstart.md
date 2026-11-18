# Reviewer Quickstart

Run these commands from the extracted repository root. The primary path
reproduces the registered evidence without a VM, container or model API.

## Install and reproduce

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
STICKS_PYTHON="$PWD/.venv/bin/python" bash run_review_check.sh
```

After installation, the reviewer gate runs offline. It regenerates the
registered evidence, checks claim chains and hashes, and runs the tests.
Limited and blocked claims remain explicitly qualified. A zero exit does
not establish that every historical campaign has executed successfully.

## Inspect admission in the graphical workbench

After installing the artifact's documented dependencies, run from its root:

```bash
.venv/bin/python scripts/run_realization_workbench.py --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`. The workbench exposes the pinned campaign inventory
and deterministic realization enumerator. It helps inspect candidate admission;
it is not evidence that a full adversarial campaign has executed successfully.
Select C0045 (ShadowRay) and click **Enumerate realizations**. The default
ceiling returns 64 realizations and reports `search_exhausted: false`. Use
**Steps** to inspect candidates, then **Download JSON** to retain the inputs,
result digest and proposal queue. The export keeps `operational_status: not_run`.

[View the captured workbench](img/realization-workbench.jpg).
Stop the local server with Ctrl-C when finished.

## Optional VM-backed laboratory

The retained laboratory runner creates virtual machines and changes lab
state. It is separate from the primary reviewer gate and requires the
provider dependencies and isolated environment described in the lab
documentation. Inspect its usage without starting a campaign:

```bash
bash artifact/run.sh --help
```

Then consult:

- [Reviewer guide](../REVIEWER_GUIDE.md)
- [Reproducibility](../REPRODUCIBILITY.md)
- [Public repository scope](../PUBLIC_REPOSITORY_SCOPE.md)

Check the host first. This is read-only and prints the exact fix for anything
that would stop the laboratory (a missing plugin, a duplicate `socket_vmnet`
daemon, too little disk, a leftover guest):

```bash
bash artifact/setup.sh
.venv/bin/python scripts/doctor.py --path lab
```

Then run the qualified live example with one command, using a new absolute path outside the repository:

```bash
bash artifact/run.sh --run-root /absolute/new/run
```

The command repeats the preflight, runs C0026 in fresh QEMU guests, observes the target separately, destroys the VMs, seals the result and verifies the sealed receipt and the CALDERA journal. It ends with `PASS` only if every stage passed. The expected scope is five observed effects and one simulated occurrence. If the campaign fails after the guests start, completion still observes, tears down and seals the failed run, and the command exits non-zero. A failed run remains retained and must not be overwritten to obtain a passing result. `bash artifact/validate.sh --run-root /absolute/new/run` re-verifies a completed run at any later time.

`--campaign 0.c0010` and `--campaign 0.costaricto` run the other campaigns with a typed laboratory contract; C0045 uses the strict effect-series runner described in the README.

Target commands use a freshly enrolled CALDERA agent. Vagrant/SSH provisions the laboratory and runs the independent observer. The retained CALDERA journal binds each target command to its result and the observed target boot.
