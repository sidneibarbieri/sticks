# Bounded Linux discovery extension

This optional catalog adds four implemented discovery procedures: system information
(T1082), user identity (T1033), processes (T1057), and files (T1083). It is separate
from the frozen primary catalog, so extending the tool does not silently change
historical experiments.

## Inspect the preserved result without Docker or a model key

From the artifact root:

```sh
python scripts/verify_linux_discovery.py release/experiments/linux_discovery/run-20260919-final
```

This checks evidence hashes, prescribed commands, command outcomes, and agreement
with observations collected by separate processes. The observation process shares
the Docker control plane; it is not an independent telemetry authority.

## Repeat the execution

Install the pinned Python requirements and start Docker. Fetch the declared image:

```sh
docker pull alpine@sha256:310c62b5e7ca5b08167e4384c68db0fd2905dd9c7493756d356e893909057601
python scripts/qualify_linux_discovery.py --output results/discovery-my-run
python scripts/verify_linux_discovery.py results/discovery-my-run
```

Choose a new output directory for every run. Existing evidence is never overwritten.
The target has no network, a read-only root filesystem, a bounded fixture directory,
a non-root user, dropped capabilities, and resource limits. Only the declared
read-only discovery commands run. The container is removed after qualification.

## What the result means

Four concrete procedures have matching observations in the declared Linux container.
The fixture and target shell are provided by the harness and recorded as initial
facts. This does not establish initial compromise, lateral movement, stealth, or
an enterprise-wide campaign. Containers share the host kernel.

The four identifiers occur in 45 steps of the pinned campaign corpus. The union
of the primary catalog and this extension indexes 297 of 1,146 steps, versus 252
in the primary catalog. These are index counts. Four qualification runs are not
45 executed campaign steps. Qualification does not establish execution of the
other 252 indexed steps either. Use `data/concretization/extensions/linux_discovery.json`
as an explicit additional catalog, rather than replacing the primary dataset.
