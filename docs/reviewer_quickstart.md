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

For the qualified live example, use a new absolute path outside the repository:

```bash
bash artifact/setup.sh
bash artifact/run.sh --run-root /absolute/new/run
bash artifact/validate.sh --run-root /absolute/new/run
```

This uses C0026, observes the target separately, destroys the created VMs and seals the result. The expected scope is five observed effects and one simulated occurrence. A process exit alone is insufficient; validation must pass on the final receipt. A failed run remains retained and must not be overwritten to obtain a passing result.

Execution transport in this example is Vagrant/SSH. A healthy Caldera is a laboratory prerequisite, not proof that it dispatched the campaign.
