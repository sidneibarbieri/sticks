# Selecting campaign coverage evidence

The coverage matrix compares the eight retained historical campaign inventories
with current campaign files, SUT profiles, registered executors and runner
summaries. These are different evidence boundaries.

The default input remains `release/evidence`. An isolated prospective run does
not update that directory. Select its evidence explicitly when diagnosing it:

```bash
python3 scripts/build_coverage_matrix.py \
  --evidence-dir /path/to/isolated-run/evidence \
  --output-dir /path/to/separate-report
```

The report records `evidence_directory`; each selected summary records
`summary_sha256`. Input directories must exist. Selected summary paths may not
escape that directory through symlinks. The command reads summaries but does
not copy, alter or merge them into frozen evidence.

For each campaign, selection uses the lexicographically largest matching run
directory name, under the selected evidence directory. This assumes the usual
timestamped runner naming convention; it does not parse timestamps or infer
which experiment is scientifically preferred. Inspect the selected path and
digest before citing a result. A digest binds bytes, not the truth of their
contents or their relationship to a sealed run.

`COMPLETE` means the selected runner summary matches campaign/SUT identifiers,
technique multiplicities, counts and successful step statuses. It does not mean
the whole laboratory cycle passed. A runner-complete campaign can still have a
failed observer, rejected finalization or incomplete teardown. Independent
effect observations and final cycle receipts must be checked separately.
Simulated executors remain simulations even when the runner succeeds.

`MISSING` means no matching evidence was selected, or required campaign/profile
files are absent. It does not establish that no execution exists elsewhere.
Do not silently combine directories to increase a coverage count. Explicitly
define the population and distinguish historical, diagnostic and prospective
experiments before reporting aggregates.
