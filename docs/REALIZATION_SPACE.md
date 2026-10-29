# Causal realization spaces

STICKS represents procedural reconstruction as a finite, versioned search problem. A
realization binds every source technique to one admitted action template, orders the
selected actions according to declared fact dependencies, and emits a causal graph plus
a reachability certificate.

The implementation deliberately does not claim to enumerate infinitely many possible
commands. Its candidate universe consists of:

1. every finite-domain binding of the versioned action-template catalog; and
2. optional externally proposed candidates that pass the same deterministic verifier.

Search limits are part of the output contract. `exhaustive` means that the finite
candidate universe was exhausted. `bounded` means that at least one realization was
found before a declared limit. `no_admissible_realization` is a fail-closed abstention.
Every generated result has `operational_status: not_run`; execution evidence must come
from the campaign runner, not from planning.

The enumerator first seeds one canonical causal schedule for each procedure assignment.
It then explores alternative topological orders. This prevents a factorial number of
orderings for one procedure assignment from hiding other admitted procedures inside a
bounded result set.

`step_realization_coverage` keeps candidate multiplicity separate from realized
multiplicity. For each source step it records the number of raw finite candidates, the
template-and-binding assignments that appear in complete realizations, distinct causal
semantics, and the positions those realizations occupy. A candidate that cannot
participate in a complete graph is not counted as a realized assignment.

`procedure_assignment_variant_count` includes the selected template identities and
bindings. `behavior_contract_variant_count` ignores template names and compares bindings,
preconditions, postconditions, evidence predicates, and fidelity ceilings. Renaming or
reimplementing an otherwise identical template therefore does not become a new behavior
contract claim.

`causal_structure_variant_count` normalizes every edge to source-step identities and ignores
the order chosen for causally independent steps. `ordering_variant_count` counts complete
topological schedules, while `graph_variant_count` counts their serialized, schedule-bearing
graph records. Thus 64 schedules of one partial order are not reported as 64 distinct causal
structures.

Retrieval traces are stored once at the realization-space level. Graph nodes reference
the corresponding hash-bound plan steps by sequence, source index, technique, and
template; they do not duplicate the plan's bindings and predicates.

## Generate a realization space

```bash
python scripts/enumerate_realization_space.py \
  --plan release/plans/C0010.procedural-plan.json \
  --bindings release/plans/C0010.binding-catalog.json \
  --output /tmp/C0010.realization-space.json \
  --maximum-realizations 64 \
  --maximum-search-states 10000
```

Optional proposals are read from a JSON list, or from an object containing a
`proposals` list. The enumerator does not call a model or accept free-form commands.
Proposal generation and deterministic admission remain separate trust domains.

Proposed action templates use a stricter promotion path:

```bash
python scripts/build_template_generation_queue.py \
  --plan release/plans/C0010.procedural-plan.json \
  --bindings release/plans/C0010.binding-catalog.json \
  --desired-procedure-assignments-per-step 2 \
  --desired-behavior-contracts-per-step 2 \
  --maximum-targets 12 \
  --output /tmp/C0010.template-generation-queue.json

python scripts/generate_template_candidates.py \
  --config /tmp/provider-config.json \
  --targets /tmp/C0010.template-generation-queue.json \
  --output-dir /tmp/template-generation

python scripts/admit_template_overlay.py \
  --generation-batch /tmp/template-generation/template-candidates.json \
  --witnesses /tmp/implementation-witnesses.json \
  --output /tmp/template-overlay.json \
  --require-bound

python scripts/enumerate_realization_space.py \
  --plan release/plans/C0010.procedural-plan.json \
  --bindings release/plans/C0010.binding-catalog.json \
  --template-overlay /tmp/template-overlay.json \
  --output /tmp/C0010.realization-space.json
```

The queue reports procedure-assignment and behavior-contract deficits separately. It creates model
targets only for procedure-assignment deficits with an existing trusted behavior contract. Each
target pins the campaign plan, binding catalog, source step, execution domain, available binding
kinds, exact fact envelope, and the contracts a proposal must match exactly. The proposer cannot
invent or recombine an effect, precondition, evidence predicate, parameter interface, domain, or
fidelity ceiling and have it admitted. Target and provider-request limits are explicit. Building
the queue makes no model call.

A schema-admitted proposal without a laboratory implementation witness remains
`planning_only`. Only `implementation_bound` overlay templates enter the realization space.
The witness binds a template to a source file hash, supported parameter kinds, and evidence
predicates. Its guarantee is limited to file integrity and the declared interface. It does
not prove semantic correctness or execution; operational evidence is still required to
validate the claimed effect.

## Interpretation boundary

A causal realization graph answers whether one declared procedure composition can
reach the requested facts under a specific binding catalog. It does not establish that
the source actor used that composition, that the source report stated every binding, or
that the realization produced the intended effects in a live SUT. Those claims require
provenance labels and operational evidence.

The current compiler creates one source step per campaign-to-technique uses-link target and
coalesces duplicate relationships to that technique. A realization therefore selects one
procedure for each compiled source step and executes each step once. Repeated occurrences,
loops, retry branches, negative effects, and failure-recovery paths require a richer source flow
or an explicitly provenance-labeled reconstruction; they are not inferred from an unordered
ATT&CK campaign profile.

Technique-set discrimination is a different problem. A small set of techniques may
distinguish two campaign labels, but that property neither reconstructs missing
procedures nor proves executability. It can prioritize evaluation cases; it cannot serve
as a procedural witness.
