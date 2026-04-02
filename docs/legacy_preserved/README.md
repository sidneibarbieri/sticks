# Legacy Preservation Notes

This directory preserves the small subset of `legacy/` material that still has
documentary or methodological value for the current STICKS artifact.

Preserved items:

- `DOD_CHECKLIST_legacy.md`
  Historical release-readiness checklist. Useful as evidence of prior reviewer
  expectations and honesty criteria, but not a canonical source for the current
  artifact state.
- `REPRODUCIBILITY_CHECKLIST_legacy.md`
  Historical list of reproducibility gaps from an earlier packaging model.
  Useful as background for migration and cleanup decisions.
- `sut_health_checker_legacy.py`
  Historical standalone SUT profile checker. Preserved as design reference only.
  The current artifact should continue to rely on canonical validation flows.

Items intentionally not preserved:

- root wrapper scripts
- archived review drafts
- paper-writing files outside the software artifact
- camera-ready tarballs
- duplicated wrapper Makefiles and shell launchers

Those materials were either redundant with the current canonical entry points,
clearly outdated, or unrelated to the software artifact.
