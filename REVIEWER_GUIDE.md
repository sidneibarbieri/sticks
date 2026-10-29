# Reviewer Guide

## Primary path

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash run_review_check.sh
```

The gate regenerates every registered record, verifies the frozen SHA-256
manifest, audits claim-to-evidence chains, checks the public surface, and runs
the packaged tests. It also recompiles all 55 released Enterprise campaign
plans in a temporary directory and compares their bytes, index, and source
provenance. A failure is terminal; no step is masked.

Inspect `release/claims/verification.json`,
`release/claims/evidence_sha256.json`, `release/experiments/`, and
`release/paper_macros.tex` after the run.

## Manuscript audit

```bash
PAPER_DIR=../paper bash run_review_check.sh
```

This also rejects unregistered references, omitted registered properties,
blocked claims, forbidden wording, and known unsupported legacy results.

## Secondary path

`bash run_review_check.sh --legacy` runs the retained infrastructure-era
measurement check. It is not part of the primary claim contract.

## C0045 compute-effect series (anonymous review)

`release/experiments/c0045_compute_effect_series/series.tar.gz` is bound by `PUBLIC_TREE_SHA256.json` and replayed by `bash run_review_check.sh`. To replay only its 20 selected cells, run `PYTHONPATH=src:. python3 -m scripts.verify_c0045_effect_series_archive --archive release/experiments/c0045_compute_effect_series/series.tar.gz`. The replay checks recorded target CPU effects and three controls per block; it does not execute a new QEMU campaign or establish historical ShadowRay fidelity. The hash-bound semantic review approves this archive for anonymous review only. Identified release requires separate approval.
