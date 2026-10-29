# Public Repository Scope

The stable contract is `run_review_check.sh`, `scripts/reproduce.py`, the
compiler/concretization/contract/evaluation modules, pinned inputs under
`data/`, frozen records under `release/experiments`, the claim ledger and
integrity manifest, and linked tests.

`CONTROLLED_COMPARISON.md` and its validators define an optional reusable
experiment contract. They support no property until a frozen run set is
registered in the claim ledger.

Local configuration, credentials, private keys, generated host traces, caches,
VM state, unselected runtime evidence, manuscript-administration files, and derived
manuscript PDFs are excluded.
Pinned third-party corpora remain byte-preserved. Incidental publication names
inside source records are corpus content, not artifact targeting; authored
surfaces remain evaluation-channel neutral.
`measurement/sut`, `lab`, and older runners are secondary compatibility material.

## Private typed-run evidence candidate

`typed-run-evidence/c0010-c0026.tar.gz` is included in the tree manifest and audited by `run_review_check.sh`. The check screens changed bytes for recognizable identifiers and secrets, and reports reference-fixture matches separately. This selected archive is a private release candidate pending content and privacy approval. The audit replays sealed receipts and recorded VM states; it does not rerun QEMU or certify historical fidelity. Receipt source hashes identify the archived run source, before the evidence archive and release metadata were added to this package.
The privacy screen compares this archive with the bundled reference manifest byte-identical to both sealed run workspaces. The receipts and source manifests are independently verified. Lexical screening does not replace semantic privacy approval.

## C0045 compute-effect series (anonymous review)

`release/experiments/c0045_compute_effect_series/series.tar.gz` is bound by `PUBLIC_TREE_SHA256.json` and replayed by `bash run_review_check.sh`. To replay only its 20 selected cells, run `PYTHONPATH=src:. python3 -m scripts.verify_c0045_effect_series_archive --archive release/experiments/c0045_compute_effect_series/series.tar.gz`. The replay checks recorded target CPU effects and three controls per block; it does not execute a new QEMU campaign or establish historical ShadowRay fidelity. The hash-bound semantic review approves this archive for anonymous review only. Identified release requires separate approval.
