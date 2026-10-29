# Architecture

The primary pipeline (1) compiles a pinned ATT&CK-in-STIX campaign into a typed
plan, (2) retrieves and enumerates all finite catalog candidates, (3) admits
candidates against an explicitly scoped fact state, (4) emits a concretized
plan with provenance and semantic hashes, and (5) certifies selected executions
against declared effects and evidence predicates.

A versioned fact registry gives every planning fact a unique semantic identity
and a closed set of permitted origins. The workbench and Stage 2 controller
reject a catalog that fails this static check. It is a modeling safeguard, not
evidence that the corresponding state held in a live environment.

Proposal and admission are separate. A human or model may propose a template,
but only the deterministic verifier can commit it. Unknown templates, wrong
techniques, and unavailable bindings fail admission and leave the plan
unchanged. Older campaign runners and VM/container helpers form a secondary
compatibility layer and are not dependencies of the primary evidence path.

The optional controlled-comparison layer emits a common hash-bound proposal
record for every arm, removes the arm label before admission, and retains a
separate assignment record for post-decision reconciliation. Its run ledger
rejects missing combinations and unverifiable success evidence. This is tested
experiment infrastructure, not a completed comparison result.
