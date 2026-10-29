# State-Fact Semantics

The finite-state planner uses exact fact identifiers. A string match is necessary
for deterministic search, but it is not sufficient to show that two identifiers
describe different states or that a state may be seeded by the SUT.

`data/concretization/fact_semantics.json` is the versioned registry for the
evaluated planning surface. Each descriptor declares:

- a stable fact identifier;
- a semantic identity: subject, predicate, and assertion kind;
- the roles in which the fact may appear; and
- the evidence class required before the fact can support a stronger claim.

The registry rejects duplicate semantic identities. This prevents a catalog from
using different identifiers for the same declared state without an explicit
semantic extension.

## Static Audit

Run the audit against the frozen deep-slice SUT catalogs:

```bash
python scripts/audit_fact_semantics.py --output /tmp/fact-semantics-audit.json
```

The report checks every fact used as a catalog initial state, catalog goal,
template precondition, or template effect. It fails when a fact is unregistered
or used in a role its descriptor forbids. Existing output is never overwritten.

The local workbench applies the same audit before it exposes a campaign as
enumeration-ready. The Stage 2 controller records audits for both the base and
post-overlay catalogs, so a proposed template cannot enter causal search with an
unregistered fact or an impermissible origin.

## Evidence Boundary

This is a static modeling control. It does not establish that a fact held in a
live SUT, that an action produced a declared effect, or that a realization is
historically faithful. A declared initial fact still requires a versioned SUT
contract. A transition or effect fact still requires lifecycle receipts and,
where specified, independent effect observation.

The registry covers only the frozen planning surface. Adding a technique,
branch, state predicate, or SUT commitment requires a deliberate registry change,
tests, and appropriate evidence; it must not be inferred from a tactic label or
an LLM proposal.

## Runtime Simulation Boundary

The legacy runtime executor for T1068 creates synthetic scenario files. Its
successful return means that those files were written, not that an exploit ran
or a privilege boundary was crossed. It produces only
`simulation:privilege_escalation_recorded`, never `access:privileged` or
`system:root_access`. This runtime marker is not an addition to the frozen
planner's fact registry. The planner's `assess-privilege-boundary` template
likewise does not grant root authority.

Historical receipts that attributed privileged capabilities to this simulation
do not establish privileged execution. A real escalation claim requires a
separate, qualified executor and observations of the target identity and
privilege transition. Creating a root-named file or starting with provisioned
administrator access cannot substitute for that evidence.

## Runtime Fidelity Labels

An executor's `fidelity.declared` value classifies its implementation. Execution
success does not independently verify that classification. New runner receipts
therefore leave `fidelity.verified` null, and campaign summaries explicitly set
`fidelity_distribution_basis` to `declared`. The distribution counts declared
labels across all recorded steps, including unsuccessful steps, not verified
historical behavior or successful effects.

Older receipts remain readable and unchanged. Their `verified` field may repeat
an executor label without an independent assessment. That legacy value must not
be interpreted as proof of fidelity. Older summary files without a distribution
basis retain their original reported labels and require receipt-level inspection
before comparison with new runs. The frozen campaign matrix is a report of those
preserved labels, not independent verification of campaign effects.
