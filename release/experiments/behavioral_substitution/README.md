# Behavioral substitution experiment (design and status)

## What this experiment is, and what it is not

STICKS does not infer the historical behavior of the adversary. It certifies a specific
procedural realization that is admissible under the available CTI constraints. The
contribution is the architecture that makes such a reconstruction explicit, verified, bound
to a declared environment, provenance-tracked, and certified by observable evidence:

    CTI -> untrusted proposer -> behavioral commitment -> deterministic verifier
        -> environment binding -> execution -> execution certification

This experiment validates one property of that architecture, and is not itself the
contribution.

## Hypothesis

When the verifier admits more than one procedural realization for the same CTI-derived
constraints, does admissibility alone determine observable behavior? Equivalently: are
co-admitted realizations still observationally distinguishable once executed under
controlled conditions? This cannot be answered from declared signatures; it requires
running the alternatives and comparing what is observed.

## Instrument (implemented and tested)

`src/evaluation/behavioral_substitution.py` provides the classifier and schema:

- `TemplateObservation` records, per alternative: substrate, whether it executed, exit
  code, evidence-predicate satisfaction, produced effects, host artifacts, and whether
  telemetry and detection were instrumented.
- `classify_observations` returns one of `behaviorally_equivalent`, `observably_distinct`,
  or `inconclusive`, following these rules:
  - fewer than two alternatives executed on an available substrate → `inconclusive`;
  - any observed dimension differs → `observably_distinct`;
  - all observed dimensions equal **and** telemetry and detection instrumented →
    `behaviorally_equivalent`;
  - equal on observed effect/evidence/artifacts but telemetry/detection not instrumented →
    `inconclusive` (equivalence on observed dimensions is not full equivalence).
- `evaluate_step` takes an injected `observe` callable, so the same classifier runs the
  real lab executor in reproduction and synthetic observations in tests.

The classifier is covered by `tests/test_behavioral_substitution.py`.

## Status: harness validation, not a campaign-derived substitution result

Admissibility depends on the fact state a template is judged against, and the three scopes
give different answers for the C0045 step realizing T1105 (see
`src/concretization/admissibility.py`):

| Scope | Admitted | Distinct evidence signatures |
|---|---|---|
| hypothetical (initial facts + every fact the catalog can produce) | 3 | 1 |
| initial (declared initial facts only) | 0 | 0 |
| **sequential (facts holding when the step is reached)** | **1** | 1 |

At the sequential state -- the scope at which the pipeline actually commits -- the verifier
admits a single realization. The three transports are co-admitted only under the
hypothetical scope, which over-admits by construction. Their execution is therefore a
**controlled validation of the execution and observation harness**, and carries no claim
about procedural ambiguity in this campaign.

Across the deeply evaluated campaign steps, using each step's own bindings, no step admitted
more than one template with distinct declared evidence signatures. This is a result about
the current catalog and the evaluated sample, not a general claim that procedural ambiguity
does not exist.

## Which alternatives were executed, and why those

The alternatives come from the deterministic verifier, not from technique-and-domain
matching. For the C0045 step realizing T1105 (Ingress Tool Transfer), the verifier admits
three realizations under that campaign's declared bindings when preconditions are evaluated
against the facts reachable in the campaign: `transfer-benign-payload`,
`transfer-staged-benign-tool`, and `transfer-over-resolved-lab-channel`.
`src/executors/local_transport_realizations.py` executes each as a real, distinct transport
on the local host -- a shell copy, a staged copy, and an HTTP transfer over loopback --
delivering a hash-pinned benign payload to an identically named destination in a separate
directory, so the destination name cannot leak template identity into the observed effect.

Two scope facts must be read with the result:

- **Sequential admissibility is narrower than reachable admissibility.** During the actual
  ordered concretization run, the plan state at that step satisfies the preconditions of
  only `transfer-benign-payload`; the other two are rejected with
  `UNSATISFIED_PRECONDITIONS` and the pipeline commits a single realization. The three-way
  multiplicity holds over facts reachable in the campaign, not at that exact execution
  state. The reachable-facts view is used deliberately because it over-admits: it gives the
  substitution hypothesis its best chance rather than assuming it away.
- **The three admitted realizations declare the same evidence signature** (evidence
  predicate `source_and_destination_hashes_match`, fidelity ceiling `adapted`). They are
  therefore evidence-equivalent by declaration; the experiment tests whether executing them
  reveals any observable difference the declaration does not capture.

## Result on the local substrate (`T1105.substitution.json`)

All three realizations deliver successfully (exit 0), satisfy the identical evidence
predicate, and leave the identical end-state filesystem artifact. The step is classified
**inconclusive**: the alternatives are equivalent with respect to the observed terminal
effect and evidence predicates, and because the local substrate captures no process or
network telemetry, the experiment cannot establish observational equivalence over the full
behavioral surface. It does not establish operational equivalence in general -- the
transport mechanism itself differs, and that difference is exactly what the uninstrumented
dimensions would expose.

## What full resolution still requires

1. **The lab substrate with telemetry.** The production executors run inside Vagrant target
   VMs (`src/executors/lab_transport.py`), and distinguishing the transports requires
   capturing network and process telemetry and detection there. Bring up the lab
   (`scripts/up_lab.sh`) and provide an `observe` callable that runs each realization in the
   VM and captures telemetry/detection in addition to effect and evidence.
2. Re-run `scripts/build_behavioral_substitution_evidence.py` against that observer; when
   telemetry and detection are instrumented, the classifier returns
   `behaviorally_equivalent` or `observably_distinct` instead of `inconclusive`.
