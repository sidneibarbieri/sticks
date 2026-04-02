# Final Review Readiness - Environment Semantics Gap Artifact

## Paper Context

This paper measures the **environment semantics gap** in structured CTI:
- whether ATT&CK/STIX bundles encode enough structured detail to derive a
  deployable System Under Test (SUT),
- where platform, software, and CVE signals remain too coarse for automated
  environment construction,
- and which parts of the resulting boundary are reproducible from the released
  corpus and audit files.

## What Reviewers Need to Demonstrate

For this paper, the essential artifact checks are:
1. rerun the measurement pipeline on the bundled ATT&CK/CAPEC/FiGHT sources,
2. regenerate the manuscript-facing values, figures, and traceability files,
3. verify that the paper tables and counts still match the generated artifacts.

The minimal review artifact for this paper is measurement-only. If a broader
research workspace also contains runtime or orchestration material, that extra
material is outside the reproducibility contract for this paper.

## Current State

### Working
- `release_check.sh` reruns the measurement pipeline end to end
- numeric invariants are validated automatically
- static manuscript tables are checked against generated audit CSVs
- bibliography policy and paper-directory hygiene are enforced
- the Paper 2 PDF rebuilds from the regenerated outputs

### Honest Limitations
- The compatibility manual-validation packet is distributed, but agreement
  metrics remain pending until independent adjudication labels are filled
- Campaign-level platform inference remains a compatibility signal, not a
  confirmed target-OS attribution claim
- The released artifact proves reproducible measurement, not turnkey replay

## Honest Claim

> The artifact provides a reproducible boundary between environment detail that
> current structured CTI already supports and detail that still requires analyst
> specification.

## Canonical Entry Point

```bash
cd sticks/measurement/sut
bash release_check.sh
```

## Status

- Measurement reproduction: YES
- Manuscript synchronization: YES
- Reviewer-facing entry point aligned with paper: YES
