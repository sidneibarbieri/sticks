# STICKS Public Artifact

This repository is the complete public artifact for the Paper 2 STICKS
environment-semantics study.

It retains two execution layers:

- a canonical smoke path for reviewer-friendly reproduction;
- a broader VM-backed path for campaign/SUT realism checks.

## Fast reviewer path

```bash
git clone https://github.com/sidneibarbieri/sticks.git
cd sticks
bash run_review_check.sh
```

## VM-backed path

```bash
bash run_vm_backed_campaign.sh 0.c0011
```

That path delegates to `scripts/run_lab_campaign.py`, which resolves the
campaign SUT profile, brings up the required VM substrate, applies
declared weaknesses and vulnerable services, executes the campaign,
regenerates evidence and paper-facing reports, and tears the lab down.

## Publication contract

- The smoke path is the canonical reproducibility promise.
- The VM-backed path is included for complete public reproduction and
  realism inspection, but should still be interpreted campaign by
  campaign rather than as a blanket historical replay guarantee.
- Heavy local VM images, overlays, and developer-only config are excluded
  on purpose; they are regenerated or provisioned by the included helpers.
- Raw frozen evidence is not bundled; the included scripts regenerate
  reviewer-visible evidence and summaries from a clean checkout.
