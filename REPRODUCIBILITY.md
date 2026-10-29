# Reproducibility Contract

The reproducible unit is a registered property in
`release/claims/ledger.json`. Each non-blocked property names its population,
support type, evidence files, tests, permitted wording, and forbidden wording.
`scripts/reproduce.py` rebuilds the evidence from tracked inputs and verifies
the frozen evidence manifest. `PUBLIC_TREE_SHA256.json` additionally binds the
complete staged repository; the reviewer gate verifies it before and after the
run, excluding only declared runtime reports and caches.

The primary path requires Python 3.11 or later and `requirements.txt`. It needs
no network after dependency installation and no API key, container runtime,
hypervisor, or external service.

Three populations remain separate: catalog coverage
(252/1146 steps), deep
admission evaluation (25 steps in three fully supported campaigns), and
selected local execution evidence (three T1105 realizations). Retained VM and
container experiments are secondary compatibility material.

The two Stage-2 runs selected in
`release/experiments/stage2_authoring/paper_runs.json` ship with their
recorded decisions. Other local runs are excluded. The offline path
rechecks admission, not model generation. The cited runs use a mutable
model tag and one records a dirty source tree, so they are exploratory
rather than clean model-reproduction evidence. Their contract-valid
draft reach is not an executed-effect count.
