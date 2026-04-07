# STICKS Artifact - Reviewer Summary

**Version:** Release Candidate
**Study:** Limits of Semantic CTI for Multi-Stage APT Emulation

## Canonical Non-Interactive Flow

From repository root:

```bash
./artifact/setup.sh
./artifact/run.sh
./artifact/validate.sh
```

Optional interactive helper:

```bash
./scripts/artifact.sh
```

## Canonical Paths

- Scripts: `scripts/`
- SUT profiles: `data/sut_profiles/`
- Evidence output: `release/evidence/`
- Consolidated matrix: `results/CAMPAIGN_SUT_FIDELITY_MATRIX.md`
- Machine-readable matrix: `results/campaign_sut_fidelity_matrix.json`

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

- Choose a campaign ID and run `python3 scripts/run_campaign.py --campaign <campaign_id>`.
- Inspect latest evidence under `release/evidence/<campaign_id>_<timestamp>/`.
- Use the consolidated matrix files in `results/` to verify campaign↔SUT validity, execution success, and fidelity distribution.

## Export Refresh

After campaign execution, run:

```bash
python3 scripts/generate_corpus_state.py
python3 scripts/generate_campaign_matrix.py
```

This refreshes:

- `results/CAMPAIGN_SUT_FIDELITY_MATRIX.md`
- `results/campaign_sut_fidelity_matrix.json`
- `results/CORPUS_STATE.md`
- `results/corpus_state.json`

## Release Freeze

For final release validation:

```bash
./artifact/setup.sh
./artifact/run.sh
./artifact/validate.sh
```

Optional VM-backed validation:

```bash
python3 scripts/run_lab_campaign.py --campaign 0.c0011 --provider qemu
```

Sanitization policy (safe by default):

```bash
bash scripts/sanitize_repo.sh
python3 scripts/check_public_surface.py
```
