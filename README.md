# STICKS Public Artifact

This repository is the complete public artifact for the STICKS
environment-semantics study.

It retains three reviewer-facing layers:

- a fast paper-claim validation path;
- a repository-local minimal working example;
- a broader VM-backed path for campaign/SUT realism checks.

## Fast reviewer path

```bash
git clone https://github.com/sidneibarbieri/sticks.git
cd sticks
bash run_review_check.sh
```

This path reruns the measurement pipeline, refreshes the released
paper-facing outputs, and checks that the synthesized values remain
consistent from the same checkout.

## Minimal working example

```bash
./artifact/setup.sh
./artifact/run.sh
./artifact/validate.sh
```

This is the smallest repository-local execution trace. It is useful
when reviewers want a lightweight run that still exercises campaign
execution and evidence generation directly.

## VM-backed path

```bash
bash run_vm_backed_campaign.sh 0.c0011
bash run_vm_backed_campaign.sh 0.shadowray
```

That path delegates to `scripts/run_lab_campaign.py`, which resolves the
campaign SUT profile, brings up the required VM substrate, applies the
declared base SUT profile, applies step-conditioned overlays for
selected techniques, executes the campaign, regenerates evidence and
synthesized reports, and tears the lab down.

## Publication contract

- The fast reviewer path is the primary reproducibility promise.
- The `artifact/` path is the minimal working example for reviewers who
  want the smallest repository-local execution trace.
- The VM-backed path is included for complete public reproduction and
  realism inspection, but should still be interpreted campaign by
  campaign rather than as a blanket historical replay guarantee.
- Heavy local VM images, overlays, and developer-only config are excluded
  on purpose; they are regenerated or provisioned by the included helpers.
- Raw frozen evidence is not bundled; the included scripts regenerate
  reviewer-visible evidence and summaries from a clean checkout.

## Runtime expectations

- Fast reviewer path: Python 3.11+, TeX with `latexmk`/`pdflatex`, and
  Poppler tools (`pdftoppm`, `pdfinfo`) on `PATH`.
- Minimal working example: Python 3.11+ only; optional Vagrant/QEMU checks
  are advisory in `artifact/setup.sh`.
- VM-backed path: Vagrant plus a supported provider (`libvirt` on Linux,
  `qemu` on macOS ARM64, or `virtualbox` where stable).
- Recommended representative realism runs:
  `bash run_vm_backed_campaign.sh 0.c0011` or
  `bash run_vm_backed_campaign.sh 0.shadowray`.
