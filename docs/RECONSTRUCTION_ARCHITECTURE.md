# Procedural reconstruction architecture

## Problem boundary

A technique identifier denotes behavior, not a unique command sequence. A procedural
reconstruction must therefore choose a finite realization from incomplete CTI while preserving
the distinction between four claims:

1. a proposal is structurally valid;
2. an implementation file is bound to the proposal;
3. the declared action composition is compatible with a specific SUT contract; and
4. an independent oracle observed the declared effects during execution.

Only the fourth claim is operational evidence. Planning outputs remain `not_run`.

There is no finite enumeration of every possible procedure for a technique. The artifact instead
defines a versioned candidate universe and records its explicit search bounds. Any report about
multiple procedures or graphs is relative to that universe.

## Considered designs

### D1: unrestricted model agent

The model writes commands, executes them, observes failures, and retries. This design has broad
surface coverage, but it mixes proposal, decision, repair, and execution authority. Its hidden
state and changing provider behavior prevent exact replay. A successful exit code also does not
prove the intended effect. D1 is rejected as the artifact's trust boundary.

### D2: fixed catalog and deterministic binding

A versioned action catalog and a finite-domain solver produce reproducible candidates. Typed facts
and an independent verifier reject invalid bindings and unreachable plans. D2 is auditable, but
catalog growth and campaign-specific completion remain manual bottlenecks. D2 remains the frozen
baseline and the trusted core.

### D3: bounded proposal with deterministic admission

D3 retains D2 and adds an untrusted, replaceable proposal source. A model may propose abstract
alternate procedure metadata under a request, token, cost, and attempt budget. The proposal must
exactly match a behavior contract already implemented in the trusted catalog. The output cannot
enter a realization until it passes schema admission and is bound to a hash-pinned laboratory
implementation. The implementation witness proves file integrity and a declared interface only;
it does not prove semantic correctness.

D3 is selected because it can expand the set of implementation-bound procedure assignments
without transferring semantic, decision, or execution authority to the model. Running several
providers can increase proposal diversity, but provider voting is not an oracle. All candidates
still cross the same deterministic boundary.

The target selector measures procedure-assignment and behavior-contract deficits separately before
any model request. It creates targets only for the former. Each context pins the source plan, SUT
binding catalog, execution domain, implemented binding kinds, exact fact envelope, existing
templates, and the exact trusted behavior contracts that a candidate may match. This removes manual
prompt construction and manual online admission while preventing a model from silently extending
trusted semantics. A new effect, precondition, evidence predicate, parameter interface, or
fidelity ceiling requires an explicit framework extension and independent validation.

## Finite-state formulation

For a source plan with steps `S`, let `A_s` be the finite set of admitted candidates for step `s`,
`F_0` the initial facts from the binding catalog, and `G` the goal facts. A search state is:

```text
q = (P, K, L)
```

where `P` is the set of pending source steps, `K` is the set of known facts, and `L` is the ordered
transition trace. A candidate `a` for step `s` induces a transition only when:

```text
s in P
technique(a) = technique(s)
domain(a) = domain(s)
requires(a) subset K
bindings(a) are typed values from the SUT catalog
```

The transition produces:

```text
(P, K, L) -> (P - {s}, K union produces(a), L + [(s, a)])
```

Before a catalog enters the workbench or Stage 2 controller, its state facts are checked against
a versioned semantic registry. Each fact has a unique subject-predicate-assertion identity and a
closed set of permitted origins: declared initial state, template precondition, template effect,
or declared goal. This check prevents silent aliasing and invalid state seeding, but it is not a
runtime truth predicate. See `FACT_SEMANTICS.md`.

An accepting state has no pending steps and satisfies `G subset K`. Every accepted trace yields a
causal directed graph. Nodes are realized actions; edges identify the fact producer and consumer.
The planning certificate independently replays the trace and hashes all declared semantics.

This state machine is monotone: transitions add facts and consume each compiled source step once.
It does not model delete effects, repeated technique occurrences, loops, retries, or conditional
failure recovery. Those constructs must be supplied by a richer, provenance-labeled source flow
before they can enter the trusted search space.

The implementation uses a depth-first search stack after seeding one canonical schedule per
procedure assignment. Seeding prevents many topological orders for one assignment from hiding
other assignments under a result bound. This is a search strategy, not a semantic claim. The
artifact records result and state bounds, whether the finite universe was exhausted, and why a
search stopped.

Reported diversity separates procedure assignments, behavior contracts, normalized causal
structures, and concrete topological schedules. Causally independent schedules remain useful for
execution planning, but they do not become new attack-graph structures merely because their linear
order differs.

## Trust-separated pipeline

```text
pinned CTI plan
    -> finite catalog retrieval
    -> measured procedure-assignment and behavior-contract deficits
    -> hash-bound campaign-and-SUT target queue
    -> bounded optional model proposals
    -> schema admission and exact trusted-contract check
    -> implementation binding
    -> typed binding enumeration
    -> finite-state causal search
    -> planning certificate and graph
    -> joint SUT compatibility certificate
    -> serial campaign-SUT execution
    -> independent effect evidence
```

The first eight stages can produce a reproducible planning result. They cannot promote
`operational_status` beyond `not_run`. The runner owns lifecycle isolation, execution, teardown,
and evidence capture. The oracle, rather than the proposing model, owns effect adjudication.

## Interfaces

The command-line enumerator accepts explicit plan, binding-catalog, candidate, overlay, and search
bound files. The Stage 2 controller composes target selection, proposal, deterministic admission,
exact implementation binding, and a post-overlay search into one hash-bound ledger. The local web
workbench exposes only frozen release objects and bounded numeric controls. It reports both
procedure-assignment and behavior-contract deficits, but it does not accept filesystem paths,
shell input, credentials, provider requests, or execution requests. Both interfaces invoke the
same realization and admission logic.

```bash
python scripts/run_realization_workbench.py
```

The server binds to `127.0.0.1:8765` by default. Its campaign inventory includes the complete
corpus index and marks absent prerequisites rather than hiding them.

## Current coverage and non-claims

The corpus contains 52 campaign records and 51 compiled procedural plans. Three campaigns have
the frozen binding catalogs needed by the evaluated deep slice: C0010, C0026, and C0045. The other
compiled plans are visible but fail closed in the workbench.

The current architecture automates online target construction, proposal admission, realization
selection, causal ordering, and declared SUT compatibility for supported inputs. It does not
eliminate human work from trusted action-template design, SUT-profile construction,
evidence-predicate definition, implementation-witness authorship, or empirical adjudication. It
does not establish historical fidelity, observational equivalence, complete campaign execution, or
analyst-effort reduction.

Hosted candidate proposal is optional and remains outside the public reviewer path. Before any
online request, the provider configuration must declare positive input and output token prices;
the request, token, and estimated-cost limits are then checked against a conservative reservation.
This prevents an unpriced or already-over-budget request from reaching the provider.
