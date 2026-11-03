# C0045 CALDERA integration repetitions

This archive retains the unchanged evidence of two cold integrations on the same ARM64 host. Each run records eight CALDERA commands, five observed target effects, three target simulations, and two local simulations. Five declared occurrences remain simulated. The observed effects concern controlled guest fixtures.

The primary `bash run_review_check.sh` path checks the archive when present. To check the retained runs alone from a development checkout, after installing the pinned requirements:

```bash
.venv/bin/python scripts/verify_caldera_integration_archive.py \
  --archive release/experiments/c0045_caldera_integration/runs.tar.gz
```

The verifier checks every retained evidence digest, observation reference, dispatch/occurrence binding and qualification record. It compares seven executor-contract fields across the two runs and checks the recorded teardown states. That command does not run the privacy screen. In a reviewer package containing `PUBLIC_TREE_SHA256.json`, add `--reference-root .` to screen host paths and credentials against the packaged reference tree; `rayuser` is the declared synthetic laboratory principal. The verifier does not contact the former VMs, independently repeat teardown, or establish a complete semantic seal.

This is an operational integration check. It is separate from `c0045_compute_effect_series/series.tar.gz`, the controlled compute-effect study. It does not add paper measurements, demonstrate historical campaign fidelity, test external exfiltration, establish portability to another host, or implement the prior-work comparison. Source revision recorded by both original qualifications: `9b712e9f`.
