# STICKS ACM CCS Artifact - Reviewer Summary

**Version:** Camera Ready  
**Paper:** Limits of Semantic CTI for Multi-Stage APT Emulation

## Canonical Non-Interactive Flow

From repository root:

```bash
./software/scripts/setup.sh
./software/scripts/run_campaign.sh 0.c0011
./software/scripts/collect_evidence.sh
```

Optional interactive helper:

```bash
./software/scripts/artifact.sh
```

## Canonical Paths

- Scripts: `software/scripts/`
- SUT profiles: `software/lab/sut_profiles/`
- Evidence output: `software/release/evidence/`
- Consolidated matrix: `software/release/CAMPAIGN_SUT_FIDELITY_MATRIX.md`
- Machine-readable matrix: `software/release/campaign_sut_fidelity_matrix.json`

## Formal Campaign Status (Latest Snapshot)

Validated campaign↔SUT pairs and latest evidence are consolidated in:

- `software/release/CAMPAIGN_SUT_FIDELITY_MATRIX.md`

Current formal set (10 campaign↔SUT pairs):

- `0.c0010`
- `0.c0011`
- `0.c0015`
- `0.c0017`
- `0.c0018`
- `0.c0021`
- `0.c0026`
- `0.c0027`
- `0.lateral_test`
- `0.pikabot_realistic`

## Methodological Honesty

Fidelity classes in this artifact:

- `faithful`: mechanism and substrate preserved
- `adapted`: mechanism preserved with controlled adaptation
- `inspired`: intent preserved, mechanism/substrate diverges

Windows-specific behavior executed on Linux substrate remains classified as `inspired` where applicable.

## Reviewer Orientation

- Choose a campaign ID and run `software/scripts/run_campaign.sh <campaign_id>`.
- Inspect latest evidence under `software/release/evidence/<campaign_id>_<timestamp>/`.
- Use the consolidated matrix files in `software/release/` to verify campaign↔SUT validity, execution success, and fidelity distribution.

## Paper-Ready Exports

After campaign execution, run:

```bash
./software/scripts/collect_evidence.sh
```

This refreshes:

- `software/release/CAMPAIGN_SUT_FIDELITY_MATRIX.md`
- `software/release/campaign_sut_fidelity_matrix.json`
- `software/release/fidelity_tables.tex`
- `software/release/fidelity_report.json`
- `software/release/CLAIM_EVIDENCE_TRACEABILITY.md`
- `software/release/claim_evidence_traceability.json`
- `software/release/paper_ready_macros.tex`
- `software/release/PAPER_READY_SUMMARY.md`
- `software/release/MITRE_SCOPE_AND_REALISM.md`

## Submission Freeze

For final camera-ready validation:

```bash
./software/scripts/submission_freeze.sh --campaign 0.c0010 --provider qemu
```

Fast mode (skip smoke run):

```bash
./software/scripts/submission_freeze.sh --skip-smoke
```

Sanitization policy (safe by default):

```bash
./software/scripts/sanitize_repo.sh
./software/scripts/sanitize_repo.sh --apply-temp
./software/scripts/sanitize_repo.sh --apply-evidence-prune --retain 2
```

