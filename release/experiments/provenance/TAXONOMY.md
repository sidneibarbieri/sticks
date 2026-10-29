# Provenance taxonomy (frozen, version 1)

This document freezes the definitions behind the per-decision provenance evidence in
`*.provenance.json`. The attribution is deterministic and carries no manual annotation;
these definitions state exactly what is counted so that a reviewer can confirm the rates
are an observed property of the contracts, not an artifact of the wording.

## Units and denominators

- **Executable binding (unit of decision):** one `(template parameter -> binding_id)`
  pair required to concretize a step. It is the smallest decision that must be filled to
  make a step executable.
- **Occurrence vs unique:** a `binding_id` reused across several steps is a separate
  decision at each step. The **primary rates are per occurrence** (a value used in three
  steps counts three times). The distinct-`binding_id` view is reported alongside, in the
  `unique_binding_*` fields, for readers who prefer decisions-as-values.
- **Denominator:** `total_binding_occurrences` for the primary rates;
  `unique_binding_count` for the secondary view. `total_steps` for the mechanism rate.

## Binding provenance (a fixed function of the declared `source`)

Each binding in a campaign's binding catalog carries a declared `source`. The class is a
fixed lookup over a closed set — there is no scoring or judgement, and an unrecognized
source raises (fail-closed) rather than defaulting to a class:

| Declared `source` | Class | Meaning |
|---|---|---|
| `stix` | `cti_evidenced` | the report named this concrete value |
| `sut` | `environment_determined` | the declared laboratory fixed it |
| `executor` | `runtime_derived` | derived at run time |
| `system_choice` | `system_introduced` | the reconstruction supplied a value the report did not and the environment did not force |

Adding a source is a deliberate taxonomy change (a new version), not a silent default.

`system_introduced` denotes **provenance, not behavioral invention or low fidelity**. A
benign toolkit, a lab host identity, or a synthetic credential is introduced by the system
but is not a hypothesis about adversary behavior. `environment_determined` values come from
the declared laboratory, not a free reconstruction choice; the two are reported separately
and must not be grouped as "reconstruction choices".

## Mechanism provenance (separate from binding provenance)

For each step, the mechanism is the action template that realizes it.

| Class | Definition |
|---|---|
| `contract_forced` | the admissible templates for the step share one declared certified effect (evidence predicates + fidelity ceiling); the proposer cannot select a different declared effect |
| `proposer_chosen` | the step admits more than one template with **distinct** declared certified effects — the only place an untrusted proposer could select a different declared effect |

A zero `proposer_chosen_mechanism_rate` characterizes the current design: mechanism
selection was **contract-constrained rather than proposer-selected** in the evaluated
workflows. It does **not** establish that alternative admissible templates would produce
identical *observed* behavior — that is an execution-level validation question, not settled
by this analysis.

## Scope

Three reconstructed campaigns (C0010, C0026, C0045), 25 steps. The taxonomy is frozen at
version 1. Any change to the source→class map, the unit of decision, or the denominator is
a new taxonomy version and must be reported as such.
