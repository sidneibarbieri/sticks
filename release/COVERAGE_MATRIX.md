# STICKS Campaign Coverage Matrix

Generated: `2026-04-07T17:19:44`

Compares the eight legacy sticks-docker campaigns against the current STICKS artifact.

**Status definitions**
- `COMPLETE` — zero failed techniques, evidence generated, provenance consistent
- `PARTIAL` — runs but at least one technique fails or evidence is incomplete
- `MISSING` — campaign or SUT profile absent, or no execution recorded

## Summary

| Metric | Value |
|---|---|
| Legacy campaigns | 8 |
| COMPLETE | 0 |
| PARTIAL | 0 |
| MISSING | 8 |

## Matrix

| Legacy Campaign | STICKS ID | Campaign File | SUT Profile | Docker Steps | STICKS Steps | Executor Coverage | Status |
|---|---|:---:|:---:|---:|---:|---:|:---:|
| APT41 DUST | `0.apt41_dust` | ✓ | ✓ | 24 | 0 | 0% | **MISSING** |
| C0010 | `0.c0010` | ✓ | ✓ | 10 | 0 | 0% | **MISSING** |
| C0026 | `0.c0026` | ✓ | ✓ | 7 | 0 | 0% | **MISSING** |
| CostaRicto | `0.costaricto` | ✓ | ✓ | 11 | 0 | 0% | **MISSING** |
| Operation MidnightEclipse | `0.operation_midnighteclipse` | ✓ | ✓ | 18 | 0 | 0% | **MISSING** |
| Outer Space | `0.outer_space` | ✓ | ✓ | 9 | 0 | 0% | **MISSING** |
| Salesforce Data Exfiltration | `0.salesforce_data_exfiltration` | ✓ | ✓ | 19 | 0 | 0% | **MISSING** |
| ShadowRay | `0.shadowray` | ✓ | ✓ | 11 | 0 | 0% | **MISSING** |

## Methodological Divergences

### APT41 DUST (`0.apt41_dust`)

- docker_techniques=24 includes redundant sub-steps merged into 13 canonical ATT&CK techniques
- Web-service C2 (T1102) and infrastructure acquisition (T1583.006) simulated as inspired; no live external traffic

### C0010 (`0.c0010`)

- Resource-development steps remain inspired; no live external provider interaction

### C0026 (`0.c0026`)

- DNS resolution override adapted to lab-only local resolver path

### CostaRicto (`0.costaricto`)

- Multi-hop proxy and external remote services remain inspired; no live C2 infrastructure

### Outer Space (`0.outer_space`)

- Satellite-themed C2 infrastructure acquisition simulated as inspired

### Salesforce Data Exfiltration (`0.salesforce_data_exfiltration`)

- SaaS API calls to Salesforce simulated as inspired; no live tenant

### ShadowRay (`0.shadowray`)

- Ray Dashboard (CVE-2023-48022) is exposed as a declared step-conditioned SUT overlay immediately before T1190, not hidden inside the base image. The overlay provisions a minimal unauthenticated HTTP stub on port 8265 that responds to /api/version and /api/jobs/ like a Ray cluster with auth disabled. If the overlay is absent, the executor still falls back to provisioning the same boundary inline inside the target VM. The boundary exercised (unauthenticated job-submission API) is methodologically equivalent to CVE-2023-48022 exploitation.


## Latest Execution Results

| STICKS ID | Status | Successful | Failed | Total | Success Rate |
|---|:---:|---:|---:|---:|---:|
| `0.apt41_dust` | **MISSING** | — | — | — | — |
| `0.c0010` | **MISSING** | — | — | — | — |
| `0.c0026` | **MISSING** | — | — | — | — |
| `0.costaricto` | **MISSING** | — | — | — | — |
| `0.operation_midnighteclipse` | **MISSING** | — | — | — | — |
| `0.outer_space` | **MISSING** | — | — | — | — |
| `0.salesforce_data_exfiltration` | **MISSING** | — | — | — | — |
| `0.shadowray` | **MISSING** | — | — | — | — |
