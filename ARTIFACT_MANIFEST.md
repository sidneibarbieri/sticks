# Public Artifact Manifest

- Repository URL is supplied by the distribution channel.

## Primary evidence path

- `scripts/reproduce.py` regenerates every registered experiment record.
- `release/claims/ledger.json` maps each property to evidence and tests.
- `release/claims/evidence_sha256.json` freezes evidence and test hashes.
- `PUBLIC_TREE_SHA256.json` freezes every shipped file outside declared runtime output.
- `run_review_check.sh` runs regeneration, integrity checks, hygiene, and tests.

## Secondary material

- `measurement/sut/` and the VM/lab helpers preserve earlier experiments.
- Run the older measurement gate with `bash run_review_check.sh --legacy`.
- That material is not evidence for a registered property unless the ledger links it.

## Excluded

Local VM state, caches, provider configuration, credentials, private keys,
unselected runtime evidence, superseded result reports, and derived
manuscript PDFs are excluded. In particular, `paper/build_artifacts/main.pdf` is
not reviewer-facing artifact evidence.

## Typed-run evidence

`typed-run-evidence/c0010-c0026.tar.gz` is included in the tree manifest and audited by `run_review_check.sh`. The check screens changed bytes for recognizable identifiers and secrets, and reports reference-fixture matches separately. This release includes the selected archive. The audit replays sealed receipts and recorded VM states; it does not rerun QEMU or certify historical fidelity. Receipt source hashes identify the archived run source, before the evidence archive and release metadata were added to this package.
The privacy screen compares this archive with the bundled reference manifest byte-identical to both sealed run workspaces. The receipts and source manifests are independently verified. Lexical screening does not replace semantic privacy approval.

## C0045 compute-effect series (anonymous review)

`release/experiments/c0045_compute_effect_series/series.tar.gz` is bound by `PUBLIC_TREE_SHA256.json` and replayed by `bash run_review_check.sh`. To replay only its 20 selected cells, run `PYTHONPATH=src:. python3 -m scripts.verify_c0045_effect_series_archive --archive release/experiments/c0045_compute_effect_series/series.tar.gz`. The replay checks recorded target CPU effects and three controls per block; it does not execute a new QEMU campaign or establish historical ShadowRay fidelity. The hash-bound semantic review approves this archive for anonymous review only. Identified release requires separate approval.
