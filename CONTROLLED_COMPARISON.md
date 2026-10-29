# Controlled Comparison Contract

This module provides the integrity substrate for a matched procedural comparison. It does not ship
an experimental result and does not treat the existing raw-versus-enriched ablation as a prior-work
comparison.

The contract requires four arms: a prior-work-style planner, STICKS proposals before admission,
STICKS proposals after admission, and execution of the admitted output through a revision-bound
consumer. The three proposal arms must use the same model artifact, prompt budget, decoding
parameters, retry budget, and timeout. The execution arm consumes the admitted output without a new
proposal call.

Every campaign, arm, and seed has exactly one run record. Failed and unsupported runs are terminal
outcomes with explicit reasons; they cannot carry success evidence. Successful runs cite relative
evidence paths and SHA-256 hashes. The validator rejects missing combinations, duplicates, altered
evidence, unequal budgets, absolute paths, and parent traversal.

A successful `sticks_autosut_executed` record has a stricter evidence contract. It must contain
exactly one typed admitted plan, one revision-bound execution handoff, one typed consumer receipt,
one typed execution-semantic bridge, and one typed independent effect observation. The admitted
plan retains the complete proposal records, including template and bindings. The semantic bridge
accepts only exact equality with a frozen concretized plan and binds each proposal to a reviewed
runtime executor digest; both hashes are part of the handoff. The admitted plan also binds the
exact `collection-lock.json`, so a Git revision cannot be attached retroactively to proposals
collected from different source bytes. The five documents must agree on
experiment, campaign, seed, handoff hash, and consumer revision. The
observation records every step as target-observed, controller-observed,
simulated, or failed, and the validator rejects an observer source revision equal to the admission
oracle revision. The observer revision is derived from the registered authority contracts and
implementation bytes named by the runtime report; it is not supplied by the experiment operator.
Distinct source hashes prevent literal authority reuse; they do not alone prove
organizational independence, observer accuracy, or causal attribution. Those remain experimental
qualification requirements.

Observer revision schema 2 includes the registered adapter source plus its
declared standalone guest probes and external predicate specification. A probe
change therefore changes the observer revision recorded in new receipts, even
when the adapter itself is unchanged. Missing dependencies fail before revision
construction. Historical receipts retain their originally recorded revisions;
this change does not retroactively qualify them or provide a complete transitive
dependency inventory for the host runtime.

New collections use lock schema 4, which records an explicit `top_p` and the Ollama
version returned by `/api/version`. The collector sends that sampling option in
each request and refuses a runtime version change before the next model call.
Resuming with different sampling or runtime metadata fails. Schema 4 also pins
the guest probes, execution scripts, runtime and observer specifications, lab
provisioning, campaign/SUT inputs, and dependency lock. Changed or added inputs
in that declared population invalidate the source lock. Hidden runtime state
such as `.vagrant` and generated Python caches is excluded. Schema 1 and 2 locks
remain readable for historical inspection; missing metadata or source coverage
is not inferred retroactively. These hashes cover declared inputs, not the
complete host operating system, package registry, or remote service state.
Schema 4 additionally writes `frozen-source/` and `frozen-source-manifest.json`
before the first model call. The manifest binds every copied input to the lock's
source-tree digest, and analysis rejects a missing or changed snapshot. This
preserves the exact declared inputs for later audit; it does not replace a
versioned environment image or make the host state reproducible.
These additions do not by themselves qualify a collection under the separate
four-arm `GeneratorBudget` manifest or validate effect-observer accuracy.

For schema 3 and 4 collections, the collector creates `comparison-manifest.json`
and a complete `comparison-ledger.json` before generation. The first binds the
four-arm design to the frozen lock and canonical action catalog. The second
starts every campaign/arm/seed group as `planned`; collecting proposal cells
alone does not promote those records to terminal execution outcomes. Existing
ledgers are checked for grid consistency and preserved on resume.
Each new proposal records the formal `GeneratorBudget` hash. Its prompt-template
field identifies the shared versioned family of arm-specific prompt builders,
not identical prompt text across treatments. Exact per-cell prompts remain in
generation receipts. The retry budget counts retries after the first request:
three transport attempts mean two retries. Thinking mode and the broader source
population remain fixed by the protocol hash over the complete collection lock.

`scripts/run_controlled_execution_arm.py` is the fail-closed operational entry point. It verifies
the frozen collection sources, requires a clean tracked artifact checkout, persists the plan,
bridge, and handoff before execution, runs the typed campaign consumer once, reparses the retained
`summary.json`, and writes the receipt and independent observation only when the returned object
matches those exact bytes. A partial directory after a runtime error is failure evidence, not a
successful cell.

Every adapter emits the same `NeutralProposalRecord`, bound to its raw output and frozen budget by
SHA-256. Its `blind` transition produces a `BlindOracleInput`, which deliberately has no arm field,
and a separate `BlindAssignment` retained by the coordinator for post-decision reconciliation. The
oracle reuses the same finite-domain verifier as the primary STICKS pipeline.

```bash
python scripts/validate_controlled_comparison.py \
  --manifest path/to/manifest.json \
  --ledger path/to/run-ledger.json \
  --evidence-root path/to/evidence

python scripts/evaluate_blind_oracle.py \
  --input path/to/blind-input.json \
  --binding-catalog release/plans/C0010.binding-catalog.json \
  --action-catalog data/concretization/action_templates.json \
  --oracle-revision ORACLE_SOURCE_SHA256 \
  --output path/to/decision.json
```

No claim is supported merely because these contracts exist. Collection requires frozen real model
artifacts, immutable producer and consumer revisions, complete run accounting, and retained negative
results.

The prospective collector (`scripts/collect_controlled_comparison.py --full`) writes
`collection-lock.json` before its first model call. It binds the selected campaign inputs, Python
source, model tag and digest read from Ollama, generation settings, seeds, and shuffle seed. A resumed
run refuses changed inputs, a changed model digest, unexpected cache cells, or a historical cache
without this lock. This protects collection integrity; it does not turn the proposal-only
`prior_work_style` arm into the prior system's execution-and-revision loop. The old September 2026
records are retained as historical measurements and are not retroactively called preregistered.
Its manifest declares `study_scope: proposal_only` and names the three proposal arms. It does not
run the fourth execution arm or measure independent SUT effects, so its outputs alone cannot
satisfy a preregistration whose primary outcome is observed target effect.
The collector sends an explicit `--thinking` mode, checks that the selected Ollama model supports
it, and includes it in the lock and budget hash. The default is `off`; a smoke test is diagnostic
only and cannot qualify a campaign or a paper result.
The collector checks the model tag before each new cell, but that lookup alone cannot prove the
server used the same model bytes during generation. Final model-image and runtime attestation remain
separate release gates.

Each newly collected cell stores the exact Ollama request and response, output hash, timestamp,
elapsed time, and attempt count alongside its typed observation. A resumed prospective run rejects
cells without that receipt, emitted cells without their complete neutral proposal record, or an
altered raw output. The complete record is required because a template label alone cannot bind the
execution arm to the selected bindings. Cells are written through a temporary
file and renamed into the cache; a leftover temporary file after interruption is treated as an
error for inspection, not silently reused. These raw exchanges are private evaluation evidence
until their content passes a separate public-surface and privacy review.

Before analyzing a new proposal-only run, audit the exact collection:

```bash
python scripts/audit_prospective_collection.py --experiment-id NEW_RUN_ID
```

The analysis command runs this preflight before reading the cache or writing `analysis.json`.
It checks the frozen source lock and, for schema 4, its sealed source snapshot, three-arm manifest, complete cache-cell identities,
raw request/response receipts, frozen model settings, replays each proposal and decision from the
raw response without a model call, and recomputes metrics from the cells. This replay uses the
same frozen planner and admission code; it is not an independent outcome oracle. It does not
reproduce the bootstrap analysis, implement the prior system's execution-feedback loop, or
establish an independently observed SUT effect. A passing preflight alone cannot qualify P17 or
the four-arm study.

The fixed C0026 concretized plan and runtime contract currently pass the semantic-bridge regression
for all six occurrences. This establishes that a future admitted plan can reach the reviewed
runtime only when its technique, template, and bindings are byte-semantically equal to the frozen
plan. It is a contract test using fixture-derived proposals, not a collected model result or an
execution-effect measurement.

The two archived September 2026 comparison manifests include C0026 but do not pin the collector
source or plan hashes. The collector available at that time paired procedural and concretized steps
by array position. In C0026, four of six techniques occupy different positions in those two plans;
therefore 60 of 375 cells in each archived run may have received another technique's procedural
context. The original observations remain unchanged. Aggregate proposal rates derived from these
runs must be treated as unqualified until the comparison is recollected with the corrected loader
and frozen inputs. This issue does not, by itself, revise separate VM execution receipts.
