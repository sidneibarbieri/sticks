# P16 Adjudication Boundary

`grounding.json` is a deterministic lexical screen over the pinned procedure excerpts. It is
not a human semantic adjudication and is not, by itself, paper-ready evidence for
`STICKS-P16`.

`protocol.v1.json` fixes the label definitions, blinded input population, and promotion rule.
Run the following after the lexical record has been regenerated:

```bash
python3 scripts/build_lateral_movement_adjudication.py
```

This produces `task_packet.v1.json`, `annotation.template.v1.json`, and `status.v1.json`.
The packet intentionally omits lexical labels. Each independent annotator copies the template
to `records/<opaque-id>.json`, uses a random identifier such as `annotator-8f2a0b17`, labels
every item without looking at the lexical output or another record, and leaves no names,
e-mail addresses, affiliations, or free-form comments in the public record.

The gate accepts the current P16 wording only when at least two complete, distinct, attested
records have exact pairwise agreement and fully confirm the frozen lexical labels. A different
human result is valuable evidence, but it does not silently rewrite the existing P16 numbers:
it requires a new protocol or a revised, separately audited claim.

The gate can verify record shape, packet binding, coverage, distinct opaque identifiers, and
reported agreement. It cannot prove that two identifiers belong to different people; that is a
research-process requirement recorded in the protocol rather than a claim made by the code.
