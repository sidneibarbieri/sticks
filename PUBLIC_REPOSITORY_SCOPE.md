# Public Repository Scope

This document defines the surface that should remain stable when the repository
is prepared for a public GitHub release or reviewer handoff.

## Reviewer-Facing Files

These files define the public entry points and should remain coherent:

- `README.md`
- `REVIEWER_GUIDE.md`
- `REPRODUCIBILITY.md`
- `MANIFEST.md`
- `ARCHITECTURE.md`
- `artifact/setup.sh`
- `artifact/run.sh`
- `artifact/validate.sh`
- `artifact/teardown.sh`

The minimal manuscript-facing tracked surfaces should also remain coherent:

- `../ACM CCS - Paper 1/results/values.tex`
- `../ACM CCS - Paper 2/results/values.tex`

## Public Execution Surface

These files and directories support the canonical artifact path:

- `scripts/run_campaign.py`
- `scripts/generate_tables.py`
- `scripts/generate_corpus_state.py`
- `scripts/audit_mitre_metadata.py`
- `scripts/audit_legacy_parity.py`
- `scripts/audit_host_leakage.py`
- `campaigns/`
- `data/campaigns/`
- `data/sut_profiles/`
- `data/stix/`
- `src/`
- `tests/`

## Optional but Retained

These components are useful for measurement or infrastructure work, but they
should be presented as optional and non-canonical:

- `lab/`
- `scripts/up_lab.sh`
- `scripts/destroy_lab.sh`
- `multi_vm_manager_2vm.py`
- `multi_vm_manager.py`
- `caldera_manager.py`
- `README_MULTI_VM.md`
- `docs/`

## Publication Blockers

The following categories should not be part of the reviewer-facing GitHub
surface:

- superseded repository mirrors such as `legacy/` and `software/`
- virtual environments and caches
- runtime QEMU images, overlays, boxes, and seed ISOs
- local `.vagrant/` machine state
- developer-local Caldera configuration such as `measurement/sut/caldera_conf/local.yml`
- generated evidence directories
- exploratory result dumps
- ad hoc local logs
- historical `removed_reports/`

## Integrity Rules

- The public README must point to the canonical smoke path first.
- Historical compatibility snapshots should live in Git history or backup
  branches, not as parallel source trees in the active repository root.
- Reviewer-facing documentation must not claim that optional VM-backed paths are
  guaranteed to be green in every checkout.
- During double-blind review, manuscript trees may stay mostly excluded, but
  the minimal macro files consumed by the papers should remain versioned when
  they are generated from canonical artifact code.
- ATT&CK, tactic, and procedure mapping should remain anchored to the current
  local MITRE bundle and the published campaign corpus.
- Claims about completeness, realism, or success rate must be grounded in the
  current reports under `results/`.

## Repository Hygiene Checks

Before publication or reviewer packaging, run:

```bash
./artifact/setup.sh
./artifact/run.sh
./artifact/validate.sh
python3 scripts/check_public_surface.py
bash scripts/sanitize_repo.sh
python3 scripts/package_complete_public_repo.py
```
